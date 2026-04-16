"""Phase 3e regression tests — aggregated pre-flight checklist."""

from __future__ import annotations

import pytest

from gorzen.services.preflight import (
    LightStatus,
    PreflightBlockedError,
    build_preflight_result,
    require_green_light,
)
from gorzen.services.risk import MissionRiskAssessment, SoraGrc


def _healthy_snapshot() -> dict:
    return {
        "connection": {
            "connected": True,
            "heartbeat_age_s": 0.5,
            "autopilot": "px4",
        },
        "status": {
            "flight_mode": "AUTO.MISSION",
            "armed": False,
            "health_ok": True,
            "vtol_state": "MC",
        },
        "gps": {"fix_type": "3D_FIX", "num_satellites": 14},
        "battery": {"remaining_pct": 85.0},
        "pre_arm_messages": [],
    }


def test_green_when_all_healthy() -> None:
    result = build_preflight_result(
        telemetry_snapshot=_healthy_snapshot(),
        mission_validation={"is_valid": True, "checks": []},
        airspace_intersections=[],
        notams=[],
        energy_budget_wh=1000.0,
        estimated_energy_wh=600.0,
    )
    assert result.status == LightStatus.GREEN
    assert result.blocking_failures == []


def test_red_when_gps_not_3d() -> None:
    snap = _healthy_snapshot()
    snap["gps"]["fix_type"] = "2D_FIX"
    result = build_preflight_result(telemetry_snapshot=snap, mission_validation=None)
    assert result.status == LightStatus.RED
    assert "gps_fix_3d_or_better" in result.blocking_failures


def test_red_when_sensors_unhealthy() -> None:
    snap = _healthy_snapshot()
    snap["status"]["health_ok"] = False
    result = build_preflight_result(telemetry_snapshot=snap, mission_validation=None)
    assert result.status == LightStatus.RED
    assert "sensors_healthy" in result.blocking_failures


def test_red_when_airspace_intersection() -> None:
    result = build_preflight_result(
        telemetry_snapshot=_healthy_snapshot(),
        mission_validation={"is_valid": True, "checks": []},
        airspace_intersections=[object()],  # any non-empty list
    )
    assert result.status == LightStatus.RED
    assert "airspace_clear" in result.blocking_failures


def test_yellow_when_notams_present_but_nothing_blocking() -> None:
    result = build_preflight_result(
        telemetry_snapshot=_healthy_snapshot(),
        mission_validation={"is_valid": True, "checks": []},
        notams=[object()],
    )
    assert result.status == LightStatus.YELLOW


def test_energy_headroom_red_below_10pct() -> None:
    result = build_preflight_result(
        telemetry_snapshot=_healthy_snapshot(),
        mission_validation={"is_valid": True, "checks": []},
        energy_budget_wh=1000.0,
        estimated_energy_wh=950.0,
    )
    assert result.status == LightStatus.RED
    assert "energy_headroom" in result.blocking_failures


def test_sora_grc_high_blocks() -> None:
    assessment = MissionRiskAssessment(
        expected_fatalities_per_hour=1.0,
        grc=SoraGrc.GRC_6,
        max_population_density=10_000.0,
        mean_population_density=100.0,
    )
    result = build_preflight_result(
        telemetry_snapshot=_healthy_snapshot(),
        mission_validation={"is_valid": True, "checks": []},
        risk_assessment=assessment,
    )
    assert result.status == LightStatus.RED
    assert "sora_ground_risk" in result.blocking_failures


def test_require_green_light_raises_on_red() -> None:
    snap = _healthy_snapshot()
    snap["gps"]["fix_type"] = "NO_FIX"
    result = build_preflight_result(telemetry_snapshot=snap, mission_validation=None)
    with pytest.raises(PreflightBlockedError):
        require_green_light(result)


def test_require_green_light_passes_on_yellow() -> None:
    result = build_preflight_result(
        telemetry_snapshot=_healthy_snapshot(),
        mission_validation={"is_valid": True, "checks": []},
        notams=[object()],
    )
    assert result.status == LightStatus.YELLOW
    require_green_light(result)  # yellow should not raise
