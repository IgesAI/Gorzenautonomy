"""Consolidated pre-flight checklist service.

The telemetry router already exposes a per-connection readiness summary
(``GET /telemetry/preflight``). This module wraps it into a mission-wide
checklist that aggregates:

* Live FC health (from :mod:`gorzen.services.mavlink_telemetry`).
* Mission validation (:mod:`gorzen.services.mission_validator`).
* Airspace / NOTAM conflicts (:mod:`gorzen.services.airspace`).
* SORA ground-risk classification (:mod:`gorzen.services.risk`).
* VTOL phase-aware energy headroom (:mod:`gorzen.solver.vtol_energy`).

The result is a ``green / yellow / red`` traffic light plus a
structured list of failing checks. ``/execution/upload`` must call
:func:`require_green_light` and refuse the upload when any blocking
check is red.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LightStatus(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass
class ChecklistItem:
    name: str
    status: LightStatus
    blocking: bool
    detail: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreflightResult:
    status: LightStatus
    items: list[ChecklistItem] = field(default_factory=list)
    blocking_failures: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == LightStatus.GREEN


class PreflightBlockedError(RuntimeError):
    """Raised by :func:`require_green_light` when a blocking check fails."""

    def __init__(self, result: PreflightResult) -> None:
        self.result = result
        super().__init__(
            "Pre-flight checklist blocked: " + ", ".join(result.blocking_failures)
        )


def build_preflight_result(
    *,
    telemetry_snapshot: dict[str, Any] | None = None,
    mission_validation: dict[str, Any] | None = None,
    airspace_intersections: list[Any] | None = None,
    notams: list[Any] | None = None,
    risk_assessment: Any | None = None,
    energy_budget_wh: float | None = None,
    estimated_energy_wh: float | None = None,
    vtol_state_required: bool = True,
) -> PreflightResult:
    """Aggregate all input signals into a traffic-light pre-flight result.

    Every argument is optional so callers can skip sources they don't have
    (e.g. no FC link in a dry-run export). Each missing source adds a
    ``yellow`` item so the operator sees exactly what wasn't checked.
    """
    items: list[ChecklistItem] = []

    # --- FC health / link ---------------------------------------------------
    if telemetry_snapshot is None:
        items.append(
            ChecklistItem(
                name="flight_controller_link",
                status=LightStatus.YELLOW,
                blocking=False,
                detail="No telemetry snapshot supplied (dry-run)",
            )
        )
    else:
        conn = telemetry_snapshot.get("connection", {})
        status = telemetry_snapshot.get("status", {})
        gps = telemetry_snapshot.get("gps", {})
        battery = telemetry_snapshot.get("battery", {})

        link_ok = bool(conn.get("connected")) and float(conn.get("heartbeat_age_s", 99.0)) < 3.0
        items.append(
            ChecklistItem(
                name="flight_controller_link",
                status=LightStatus.GREEN if link_ok else LightStatus.RED,
                blocking=True,
                detail=(
                    f"connected={conn.get('connected')} hb_age={conn.get('heartbeat_age_s')}s"
                ),
            )
        )
        autopilot = conn.get("autopilot", "unknown")
        items.append(
            ChecklistItem(
                name="autopilot_identified",
                status=LightStatus.GREEN if autopilot in ("px4", "ardupilot") else LightStatus.YELLOW,
                blocking=False,
                detail=f"autopilot={autopilot}",
            )
        )
        gps_fix = gps.get("fix_type")
        gps_ok = gps_fix in ("3D_FIX", "DGPS", "RTK_FLOAT", "RTK_FIXED")
        items.append(
            ChecklistItem(
                name="gps_fix_3d_or_better",
                status=LightStatus.GREEN if gps_ok else LightStatus.RED,
                blocking=True,
                detail=f"fix={gps_fix} sats={gps.get('num_satellites')}",
            )
        )
        items.append(
            ChecklistItem(
                name="sensors_healthy",
                status=LightStatus.GREEN if status.get("health_ok") else LightStatus.RED,
                blocking=True,
                detail=f"health_ok={status.get('health_ok')}",
            )
        )
        batt_pct = battery.get("remaining_pct")
        batt_ok = isinstance(batt_pct, (int, float)) and batt_pct >= 30.0
        items.append(
            ChecklistItem(
                name="battery_above_reserve",
                status=LightStatus.GREEN if batt_ok else LightStatus.RED,
                blocking=True,
                detail=f"battery_pct={batt_pct}",
            )
        )
        if vtol_state_required:
            vtol_state = status.get("vtol_state")
            if vtol_state == "MC":
                vtol_status = LightStatus.GREEN
            elif vtol_state in ("FW", "TRANSITION_TO_FW", "TRANSITION_TO_MC"):
                vtol_status = LightStatus.YELLOW
            else:
                vtol_status = LightStatus.RED
            items.append(
                ChecklistItem(
                    name="vtol_ready_to_takeoff",
                    status=vtol_status,
                    blocking=vtol_status == LightStatus.RED,
                    detail=f"vtol_state={vtol_state}",
                )
            )
        prearm = telemetry_snapshot.get("pre_arm_messages", [])
        hot = [m for m in prearm[:4] if "FAIL" in m.upper() or "REFUS" in m.upper()]
        items.append(
            ChecklistItem(
                name="no_recent_prearm_failures",
                status=LightStatus.RED if hot else LightStatus.GREEN,
                blocking=bool(hot),
                detail=", ".join(hot) if hot else "no recent pre-arm failures",
            )
        )

    # --- Mission validation -------------------------------------------------
    if mission_validation is None:
        items.append(
            ChecklistItem(
                name="mission_validation",
                status=LightStatus.YELLOW,
                blocking=False,
                detail="No mission_validation provided",
            )
        )
    else:
        is_valid = bool(mission_validation.get("is_valid"))
        failing_checks = [
            c.get("name", "?")
            for c in mission_validation.get("checks", [])
            if not c.get("passed", False)
        ]
        items.append(
            ChecklistItem(
                name="mission_validation",
                status=LightStatus.GREEN if is_valid else LightStatus.RED,
                blocking=True,
                detail=f"failing={failing_checks}" if failing_checks else "all checks passed",
                metadata={"failing_checks": failing_checks},
            )
        )

    # --- Airspace -----------------------------------------------------------
    if airspace_intersections:
        items.append(
            ChecklistItem(
                name="airspace_clear",
                status=LightStatus.RED,
                blocking=True,
                detail=f"{len(airspace_intersections)} intersection(s) with restricted airspace",
                metadata={"count": len(airspace_intersections)},
            )
        )
    else:
        items.append(
            ChecklistItem(
                name="airspace_clear",
                status=LightStatus.GREEN,
                blocking=True,
                detail="No restricted airspace on route",
            )
        )

    # --- NOTAMs -------------------------------------------------------------
    if notams:
        items.append(
            ChecklistItem(
                name="notams_clear",
                status=LightStatus.YELLOW,
                blocking=False,
                detail=f"{len(notams)} active NOTAM(s) near route — review required",
                metadata={"count": len(notams)},
            )
        )
    else:
        items.append(
            ChecklistItem(
                name="notams_clear",
                status=LightStatus.GREEN,
                blocking=False,
                detail="No active NOTAMs within mission bbox",
            )
        )

    # --- SORA risk ----------------------------------------------------------
    if risk_assessment is not None:
        grc_value = int(getattr(risk_assessment.grc, "value", risk_assessment.grc))
        if grc_value <= 3:
            risk_status = LightStatus.GREEN
        elif grc_value <= 4:
            risk_status = LightStatus.YELLOW
        else:
            risk_status = LightStatus.RED
        items.append(
            ChecklistItem(
                name="sora_ground_risk",
                status=risk_status,
                blocking=risk_status == LightStatus.RED,
                detail=(
                    f"GRC={grc_value}, peak_density="
                    f"{risk_assessment.max_population_density:.1f} p/km², "
                    f"E[fatalities]={risk_assessment.expected_fatalities_per_hour:.2e}/hr"
                ),
                metadata={
                    "grc": grc_value,
                    "expected_fatalities_per_hour": float(
                        risk_assessment.expected_fatalities_per_hour
                    ),
                },
            )
        )

    # --- Energy headroom ----------------------------------------------------
    if energy_budget_wh is not None and estimated_energy_wh is not None:
        reserve_pct = 1.0 - estimated_energy_wh / max(energy_budget_wh, 1e-6)
        if reserve_pct >= 0.2:
            en_status = LightStatus.GREEN
        elif reserve_pct >= 0.1:
            en_status = LightStatus.YELLOW
        else:
            en_status = LightStatus.RED
        items.append(
            ChecklistItem(
                name="energy_headroom",
                status=en_status,
                blocking=en_status == LightStatus.RED,
                detail=(
                    f"estimated={estimated_energy_wh:.1f} Wh, "
                    f"budget={energy_budget_wh:.1f} Wh, "
                    f"reserve={reserve_pct * 100:.0f}%"
                ),
                metadata={"reserve_pct": float(reserve_pct)},
            )
        )

    # --- Aggregate ----------------------------------------------------------
    blocking_failures = [
        i.name for i in items if i.blocking and i.status == LightStatus.RED
    ]
    overall = (
        LightStatus.RED
        if blocking_failures
        else (
            LightStatus.YELLOW
            if any(i.status == LightStatus.YELLOW for i in items)
            else LightStatus.GREEN
        )
    )
    return PreflightResult(
        status=overall,
        items=items,
        blocking_failures=blocking_failures,
    )


def require_green_light(result: PreflightResult) -> None:
    """Raise :class:`PreflightBlockedError` unless the checklist is green.

    Yellow (warning) passes; only red blocking failures stop the mission.
    Call this right before MAVSDK ``mission_raw.upload_mission``.
    """
    if result.status == LightStatus.RED:
        raise PreflightBlockedError(result)


__all__ = [
    "ChecklistItem",
    "LightStatus",
    "PreflightBlockedError",
    "PreflightResult",
    "build_preflight_result",
    "require_green_light",
]
