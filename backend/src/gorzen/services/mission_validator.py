"""Pre-flight mission validation service.

Validates a MissionPlan against aircraft twin parameters and
environmental conditions before execution.  Returns a structured
report of pass/fail checks with limits and measured values so the
operator can review and override as needed.

ENFORCEMENT RULES:
- Missing data = FAIL (not skip).  If terrain, geofence, sensor, or
  environmental data is unavailable, the check FAILS so that the
  operator must explicitly acknowledge the gap.
- Every output traces to a source parameter.
- No silent fallback values.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from gorzen.schemas.mission import MissionPlan
from gorzen.validation.parameter_validator import (
    Violation,
    ViolationType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

MIN_AGL_CLEARANCE_M = 10.0
ENERGY_RESERVE_FACTOR = 0.80  # 20 % reserve → usable = 80 %


@dataclass
class CheckResult:
    """Outcome of a single validation check."""

    name: str
    passed: bool
    value: float
    limit: float
    unit: str
    detail: str


@dataclass
class ValidationResult:
    """Aggregate pre-flight validation outcome."""

    is_valid: bool
    checks: list[CheckResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get(params: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Walk nested dicts or flat keys, returning the first hit."""
    for key in keys:
        parts = key.split(".")
        obj: Any = params
        for p in parts:
            if isinstance(obj, dict):
                obj = obj.get(p)
            else:
                obj = None
                break
        if obj is not None:
            return _unwrap(obj)
    return default


def _unwrap(val: Any) -> Any:
    """If *val* is a TypedParameter-like dict with a ``value`` key, return the inner value."""
    if isinstance(val, dict) and "value" in val:
        return val["value"]
    return val


def _point_in_polygon(lat: float, lon: float, polygon: Sequence[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test (lat/lon treated as planar coords)."""
    n = len(polygon)
    inside = False
    x, y = lon, lat
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][1], polygon[i][0]  # lon, lat
        xj, yj = polygon[j][1], polygon[j][0]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_energy_budget(
    plan: MissionPlan,
    params: dict[str, Any],
) -> CheckResult:
    """Total estimated energy must fit within battery/fuel capacity with 20 % reserve."""
    capacity_wh = _get(
        params,
        "energy_capacity_wh",
        "energy.capacity_ah",
        "battery_capacity_wh",
        default=0.0,
    )
    # Derive Wh from Ah × V when stored as separate fields
    if capacity_wh == 0.0:
        ah = _get(params, "energy.capacity_ah", "capacity_ah", default=0.0)
        volts = _get(params, "energy.nominal_voltage_v", "nominal_voltage_v", default=0.0)
        if ah and volts:
            capacity_wh = float(ah) * float(volts)

    # For ICE/hybrid twins expressed in litres + density + heating value
    if capacity_wh == 0.0:
        litres = _get(params, "fuel_system.tank_capacity_l", "fuel_capacity_l", default=0.0)
        density = _get(params, "fuel_system.fuel_density_kg_l", "fuel_density_kg_l", default=0.81)
        heating_wh_per_kg = _get(params, "fuel_heating_value_wh_per_kg", default=12_000.0)
        if litres:
            capacity_wh = float(litres) * float(density) * float(heating_wh_per_kg)

    usable_wh = float(capacity_wh) * ENERGY_RESERVE_FACTOR
    estimated = plan.estimated_energy_wh

    return CheckResult(
        name="energy_budget",
        passed=estimated <= usable_wh,
        value=round(estimated, 1),
        limit=round(usable_wh, 1),
        unit="Wh",
        detail=(
            f"Estimated {estimated:.1f} Wh vs {usable_wh:.1f} Wh usable "
            f"({ENERGY_RESERVE_FACTOR * 100:.0f}% of {capacity_wh:.1f} Wh capacity)"
        ),
    )


def _check_terrain_clearance(
    plan: MissionPlan,
    terrain_elevations_m: Sequence[float] | None,
) -> CheckResult:
    """Every waypoint must be ≥ MIN_AGL_CLEARANCE_M above terrain."""
    if not plan.waypoints:
        return CheckResult(
            name="terrain_clearance",
            passed=True,
            value=0.0,
            limit=MIN_AGL_CLEARANCE_M,
            unit="m AGL",
            detail="No waypoints to check",
        )

    if terrain_elevations_m is None or len(terrain_elevations_m) != len(plan.waypoints):
        return CheckResult(
            name="terrain_clearance",
            passed=False,
            value=0.0,
            limit=MIN_AGL_CLEARANCE_M,
            unit="m AGL",
            detail="INSUFFICIENT_DATA: Terrain elevation data required but not provided",
        )

    min_clearance = math.inf
    for wp, ground_elev in zip(plan.waypoints, terrain_elevations_m):
        agl = wp.altitude_m - ground_elev
        if agl < min_clearance:
            min_clearance = agl

    return CheckResult(
        name="terrain_clearance",
        passed=min_clearance >= MIN_AGL_CLEARANCE_M,
        value=round(min_clearance, 1),
        limit=MIN_AGL_CLEARANCE_M,
        unit="m AGL",
        detail=f"Minimum clearance {min_clearance:.1f} m AGL (required ≥ {MIN_AGL_CLEARANCE_M} m)",
    )


def _check_geofence(
    plan: MissionPlan,
    geofence: Sequence[tuple[float, float]] | None,
) -> CheckResult:
    """All waypoints must fall inside the geofence polygon (if provided)."""
    if not geofence:
        return CheckResult(
            name="geofence",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="",
            detail="INSUFFICIENT_DATA: Geofence polygon required but not defined",
        )

    violations = 0
    for wp in plan.waypoints:
        if not _point_in_polygon(wp.latitude_deg, wp.longitude_deg, geofence):
            violations += 1

    return CheckResult(
        name="geofence",
        passed=violations == 0,
        value=float(violations),
        limit=0.0,
        unit="violations",
        detail=(
            "All waypoints inside geofence"
            if violations == 0
            else f"{violations} waypoint(s) outside geofence boundary"
        ),
    )


def _check_speed_limits(
    plan: MissionPlan,
    params: dict[str, Any],
) -> CheckResult:
    """No waypoint speed may exceed the aircraft maximum speed."""
    max_speed = _get(
        params,
        "airframe.max_speed_kts",
        "max_speed_ms",
        default=0.0,
    )
    max_speed = float(max_speed)

    # Convert knots → m/s when the twin stores speed in knots
    if _get(params, "airframe.max_speed_kts") is not None:
        max_speed_ms = max_speed * 0.514444
    else:
        max_speed_ms = max_speed

    if max_speed_ms <= 0:
        return CheckResult(
            name="speed_limits",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="m/s",
            detail="INSUFFICIENT_DATA: Aircraft max speed not specified",
        )

    fastest = max(
        (wp.speed_ms for wp in plan.waypoints if wp.speed_ms is not None),
        default=0.0,
    )

    return CheckResult(
        name="speed_limits",
        passed=fastest <= max_speed_ms,
        value=round(fastest, 1),
        limit=round(max_speed_ms, 1),
        unit="m/s",
        detail=f"Fastest waypoint {fastest:.1f} m/s vs aircraft limit {max_speed_ms:.1f} m/s",
    )


def _check_endurance(
    plan: MissionPlan,
    params: dict[str, Any],
) -> CheckResult:
    """Mission duration must not exceed aircraft endurance."""
    endurance_min = _get(
        params,
        "endurance_min",
        "airframe.max_endurance_hr",
        default=0.0,
    )
    endurance_min = float(endurance_min)

    # Normalise to seconds
    if _get(params, "airframe.max_endurance_hr") is not None:
        endurance_s = endurance_min * 3600.0
    else:
        endurance_s = endurance_min * 60.0  # frontend stores minutes

    if endurance_s <= 0:
        return CheckResult(
            name="endurance",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="s",
            detail="INSUFFICIENT_DATA: Aircraft endurance not specified",
        )

    return CheckResult(
        name="endurance",
        passed=plan.estimated_duration_s <= endurance_s,
        value=round(plan.estimated_duration_s, 1),
        limit=round(endurance_s, 1),
        unit="s",
        detail=(
            f"Mission {plan.estimated_duration_s:.0f}s vs endurance "
            f"{endurance_s:.0f}s ({endurance_s / 60:.0f} min)"
        ),
    )


def _check_wind_tolerance(
    params: dict[str, Any],
    environment: dict[str, Any] | None,
) -> CheckResult:
    """Current wind conditions must be within aircraft limits."""
    wind_limit = _get(params, "wind_limit_ms", "airframe.max_crosswind_kts", default=0.0)
    wind_limit = float(wind_limit)

    # Convert knots → m/s if sourced from subsystem config
    if _get(params, "airframe.max_crosswind_kts") is not None:
        wind_limit_ms = wind_limit * 0.514444
    else:
        wind_limit_ms = wind_limit

    if wind_limit_ms <= 0:
        return CheckResult(
            name="wind_tolerance",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="m/s",
            detail="INSUFFICIENT_DATA: Aircraft wind limit not specified",
        )

    wind_speed = 0.0
    if environment:
        wind_speed = float(_get(environment, "wind_speed_ms", "wind.speed_ms", default=0.0) or 0.0)
        gusts = float(_get(environment, "wind_gusts_ms", "wind.gusts_ms", default=0.0) or 0.0)
        wind_speed = max(wind_speed, gusts)

    return CheckResult(
        name="wind_tolerance",
        passed=wind_speed <= wind_limit_ms,
        value=round(wind_speed, 1),
        limit=round(wind_limit_ms, 1),
        unit="m/s",
        detail=f"Wind {wind_speed:.1f} m/s vs limit {wind_limit_ms:.1f} m/s",
    )


def _check_temperature(
    params: dict[str, Any],
    environment: dict[str, Any] | None,
) -> CheckResult:
    """Operating temperature must be within aircraft limits."""
    temp_min = _get(
        params,
        "operating_temp_min_c",
        "airframe.min_operating_temp_c",
        default=None,
    )
    temp_max = _get(
        params,
        "operating_temp_max_c",
        "airframe.max_operating_temp_c",
        default=None,
    )

    if temp_min is None and temp_max is None:
        return CheckResult(
            name="temperature",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="°C",
            detail="INSUFFICIENT_DATA: Aircraft temperature limits not specified",
        )

    temp_min_c = float(temp_min) if temp_min is not None else -273.0
    temp_max_c = float(temp_max) if temp_max is not None else 100.0

    if not environment or _get(environment, "temperature_c", "temperature", default=None) is None:
        return CheckResult(
            name="temperature",
            passed=False,
            value=0.0,
            limit=round(temp_max_c, 1),
            unit="°C",
            detail="INSUFFICIENT_DATA: Current temperature not provided",
        )

    current_temp = float(_get(environment, "temperature_c", "temperature", default=0.0) or 0.0)

    in_range = temp_min_c <= current_temp <= temp_max_c

    return CheckResult(
        name="temperature",
        passed=in_range,
        value=round(current_temp, 1),
        limit=round(temp_max_c, 1),
        unit="°C",
        detail=f"Temp {current_temp:.1f} °C vs range [{temp_min_c:.0f}, {temp_max_c:.0f}] °C",
    )


def _check_payload_capacity(
    params: dict[str, Any],
    required_payload_kg: float | None,
) -> CheckResult:
    """Required payload mass must not exceed aircraft maximum payload."""
    max_payload = _get(
        params,
        "payload_max_kg",
        "airframe.payload_capacity_nose_kg",
        default=0.0,
    )
    max_payload = float(max_payload)

    if max_payload <= 0:
        return CheckResult(
            name="payload_capacity",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="kg",
            detail="INSUFFICIENT_DATA: Aircraft payload limit not specified",
        )

    required = float(required_payload_kg or 0.0)

    return CheckResult(
        name="payload_capacity",
        passed=required <= max_payload,
        value=round(required, 2),
        limit=round(max_payload, 2),
        unit="kg",
        detail=f"Required {required:.2f} kg vs max {max_payload:.2f} kg",
    )


# ---------------------------------------------------------------------------
# Perception / detection checks
# ---------------------------------------------------------------------------


def _compute_gsd_m(
    altitude_m: float, sensor_width_mm: float, focal_length_mm: float, pixel_width: float
) -> float:
    """GSD in metres/pixel.  Same formula as GSDModel.evaluate."""
    return (sensor_width_mm * altitude_m) / (focal_length_mm * pixel_width)


def _check_detection_capability(
    plan: MissionPlan,
    params: dict[str, Any],
    target_size_m: float | None,
    min_pixels_on_target: float | None,
) -> CheckResult:
    """Verify pixels-on-target meets detection requirements at each waypoint altitude."""
    sw = _get(params, "sensor_width_mm", "payload.sensor_width_mm", default=None)
    fl = _get(params, "focal_length_mm", "payload.focal_length_mm", default=None)
    px_w = _get(params, "pixel_width", "payload.pixel_width", default=None)

    if sw is None or fl is None or px_w is None:
        return CheckResult(
            name="detection_capability",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="px",
            detail="INSUFFICIENT_DATA: Sensor parameters (sensor_width_mm, focal_length_mm, pixel_width) required",
        )
    if target_size_m is None or target_size_m <= 0:
        return CheckResult(
            name="detection_capability",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="px",
            detail="INSUFFICIENT_DATA: target_size_m required for detection validation",
        )
    if min_pixels_on_target is None or min_pixels_on_target <= 0:
        return CheckResult(
            name="detection_capability",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="px",
            detail="INSUFFICIENT_DATA: min_pixels_on_target required for detection validation",
        )

    sw_f = float(sw)
    fl_f = float(fl)
    px_w_f = float(px_w)

    worst_pot = math.inf
    for wp in plan.waypoints:
        gsd_m = _compute_gsd_m(wp.altitude_m, sw_f, fl_f, px_w_f)
        pot = target_size_m / gsd_m if gsd_m > 0 else 0.0
        worst_pot = min(worst_pot, pot)

    if worst_pot == math.inf:
        worst_pot = 0.0

    return CheckResult(
        name="detection_capability",
        passed=worst_pot >= min_pixels_on_target,
        value=round(worst_pot, 1),
        limit=round(min_pixels_on_target, 1),
        unit="px on target",
        detail=(
            f"Worst-case {worst_pot:.1f} pixels on target vs required {min_pixels_on_target:.1f} — "
            f"target size {target_size_m * 1000:.0f} mm"
        ),
    )


def _check_gsd(
    plan: MissionPlan,
    params: dict[str, Any],
    max_gsd_cm_px: float | None,
) -> CheckResult:
    """Verify GSD at each waypoint altitude meets the resolution requirement."""
    sw = _get(params, "sensor_width_mm", "payload.sensor_width_mm", default=None)
    fl = _get(params, "focal_length_mm", "payload.focal_length_mm", default=None)
    px_w = _get(params, "pixel_width", "payload.pixel_width", default=None)

    if sw is None or fl is None or px_w is None:
        return CheckResult(
            name="gsd",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="cm/px",
            detail="INSUFFICIENT_DATA: Sensor parameters required for GSD validation",
        )
    if max_gsd_cm_px is None or max_gsd_cm_px <= 0:
        return CheckResult(
            name="gsd",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="cm/px",
            detail="INSUFFICIENT_DATA: max_gsd_cm_px required for GSD validation",
        )

    sw_f = float(sw)
    fl_f = float(fl)
    px_w_f = float(px_w)

    worst_gsd_cm = 0.0
    for wp in plan.waypoints:
        gsd_m = _compute_gsd_m(wp.altitude_m, sw_f, fl_f, px_w_f)
        gsd_cm = gsd_m * 100.0
        worst_gsd_cm = max(worst_gsd_cm, gsd_cm)

    return CheckResult(
        name="gsd",
        passed=worst_gsd_cm <= max_gsd_cm_px,
        value=round(worst_gsd_cm, 3),
        limit=round(max_gsd_cm_px, 3),
        unit="cm/px",
        detail=f"Worst-case GSD {worst_gsd_cm:.3f} cm/px vs limit {max_gsd_cm_px:.3f} cm/px",
    )


def _check_motion_blur(
    plan: MissionPlan,
    params: dict[str, Any],
    exposure_time_s: float | None,
    max_blur_px: float | None,
) -> CheckResult:
    """Verify motion blur at each waypoint stays within the pixel budget.

    blur_px = (ground_speed_ms * exposure_time_s) / gsd_m
    """
    sw = _get(params, "sensor_width_mm", "payload.sensor_width_mm", default=None)
    fl = _get(params, "focal_length_mm", "payload.focal_length_mm", default=None)
    px_w = _get(params, "pixel_width", "payload.pixel_width", default=None)

    if sw is None or fl is None or px_w is None:
        return CheckResult(
            name="motion_blur",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="px",
            detail="INSUFFICIENT_DATA: Sensor parameters required for motion blur validation",
        )
    if exposure_time_s is None or exposure_time_s <= 0:
        return CheckResult(
            name="motion_blur",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="px",
            detail="INSUFFICIENT_DATA: exposure_time_s required (must be explicit, not assumed)",
        )
    if max_blur_px is None or max_blur_px <= 0:
        return CheckResult(
            name="motion_blur",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="px",
            detail="INSUFFICIENT_DATA: max_blur_px required for motion blur validation",
        )

    sw_f = float(sw)
    fl_f = float(fl)
    px_w_f = float(px_w)

    worst_blur = 0.0
    for wp in plan.waypoints:
        speed_ms = wp.speed_ms if wp.speed_ms is not None else 0.0
        if speed_ms <= 0:
            continue
        gsd_m = _compute_gsd_m(wp.altitude_m, sw_f, fl_f, px_w_f)
        if gsd_m <= 0:
            continue
        blur_px = (speed_ms * exposure_time_s) / gsd_m
        worst_blur = max(worst_blur, blur_px)

    return CheckResult(
        name="motion_blur",
        passed=worst_blur <= max_blur_px,
        value=round(worst_blur, 3),
        limit=round(max_blur_px, 3),
        unit="px",
        detail=(
            f"Worst-case blur {worst_blur:.3f} px vs limit {max_blur_px:.3f} px "
            f"(exposure 1/{round(1.0 / exposure_time_s)}s)"
        ),
    )


def _check_frame_overlap(
    plan: MissionPlan,
    params: dict[str, Any],
    min_overlap_pct: float | None,
    trigger_interval_m: float | None,
) -> CheckResult:
    """Verify frame overlap meets coverage requirements.

    overlap_pct = 1 - (trigger_interval_m / footprint_along_m)
    footprint_along_m = gsd_m * pixel_height
    """
    sw = _get(params, "sensor_width_mm", "payload.sensor_width_mm", default=None)
    sh = _get(params, "sensor_height_mm", "payload.sensor_height_mm", default=None)
    fl = _get(params, "focal_length_mm", "payload.focal_length_mm", default=None)
    px_w = _get(params, "pixel_width", "payload.pixel_width", default=None)
    px_h = _get(params, "pixel_height", "payload.pixel_height", default=None)

    if any(v is None for v in (sw, sh, fl, px_w, px_h)):
        return CheckResult(
            name="frame_overlap",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="%",
            detail="INSUFFICIENT_DATA: Full sensor parameters required for overlap validation",
        )
    if min_overlap_pct is None:
        return CheckResult(
            name="frame_overlap",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="%",
            detail="INSUFFICIENT_DATA: min_overlap_pct required for overlap validation",
        )
    if trigger_interval_m is None or trigger_interval_m <= 0:
        return CheckResult(
            name="frame_overlap",
            passed=False,
            value=0.0,
            limit=0.0,
            unit="%",
            detail="INSUFFICIENT_DATA: trigger_interval_m required for overlap validation",
        )

    sh_f = float(sh)
    fl_f = float(fl)
    px_h_f = float(px_h)

    worst_overlap = 100.0
    for wp in plan.waypoints:
        gsd_h_m = (sh_f * wp.altitude_m) / (fl_f * px_h_f)
        footprint_along_m = gsd_h_m * px_h_f
        if footprint_along_m <= 0:
            continue
        overlap_pct = (1.0 - trigger_interval_m / footprint_along_m) * 100.0
        worst_overlap = min(worst_overlap, overlap_pct)

    return CheckResult(
        name="frame_overlap",
        passed=worst_overlap >= min_overlap_pct,
        value=round(worst_overlap, 1),
        limit=round(min_overlap_pct, 1),
        unit="%",
        detail=f"Worst-case overlap {worst_overlap:.1f}% vs required {min_overlap_pct:.1f}%",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_mission(
    plan: MissionPlan,
    twin_params: dict[str, Any],
    *,
    environment: dict[str, Any] | None = None,
    geofence: Sequence[tuple[float, float]] | None = None,
    terrain_elevations_m: Sequence[float] | None = None,
    required_payload_kg: float | None = None,
    target_size_m: float | None = None,
    min_pixels_on_target: float | None = None,
    max_gsd_cm_px: float | None = None,
    exposure_time_s: float | None = None,
    max_blur_px: float | None = None,
    min_overlap_pct: float | None = None,
    trigger_interval_m: float | None = None,
) -> ValidationResult:
    """Run all pre-flight checks and return a structured validation report.

    Parameters
    ----------
    plan:
        The mission plan to validate (from ``gorzen.schemas.mission``).
    twin_params:
        Aircraft digital-twin parameters dict.  Accepts both the flat
        frontend preset format (``max_speed_ms``, ``endurance_min``, …)
        and the nested subsystem format (``airframe.max_speed_kts``, …).
    environment:
        Current weather / atmospheric conditions dict.
    geofence:
        Bounding polygon as ``[(lat, lon), …]``.
    terrain_elevations_m:
        Ground elevations (MSL) for each waypoint — same order and length
        as ``plan.waypoints``.
    required_payload_kg:
        Total payload mass the mission requires.
    target_size_m:
        Smallest target feature extent in metres (for POT check).
    min_pixels_on_target:
        Minimum required pixels on the target for detection.
    max_gsd_cm_px:
        Maximum acceptable GSD in cm/px.
    exposure_time_s:
        Camera exposure time in seconds (MUST be explicit, not assumed).
    max_blur_px:
        Maximum acceptable motion blur in pixels.
    min_overlap_pct:
        Minimum required forward overlap percentage.
    trigger_interval_m:
        Distance between camera triggers in metres.
    """
    checks: list[CheckResult] = [
        _check_energy_budget(plan, twin_params),
        _check_terrain_clearance(plan, terrain_elevations_m),
        _check_geofence(plan, geofence),
        _check_speed_limits(plan, twin_params),
        _check_endurance(plan, twin_params),
        _check_wind_tolerance(twin_params, environment),
        _check_temperature(twin_params, environment),
        _check_payload_capacity(twin_params, required_payload_kg),
        _check_gsd(plan, twin_params, max_gsd_cm_px),
        _check_detection_capability(plan, twin_params, target_size_m, min_pixels_on_target),
        _check_motion_blur(plan, twin_params, exposure_time_s, max_blur_px),
        _check_frame_overlap(plan, twin_params, min_overlap_pct, trigger_interval_m),
    ]

    warnings: list[str] = []
    violations: list[Violation] = []

    for c in checks:
        if not c.passed:
            warnings.append(f"FAIL [{c.name}]: {c.detail}")
            if "INSUFFICIENT_DATA" in c.detail:
                violations.append(
                    Violation(
                        violation_type=ViolationType.MISSING_DATA,
                        parameter=c.name,
                        location="mission_validator",
                        impact=c.detail,
                        correction=f"Provide required data for {c.name} check",
                    )
                )

    insufficient = [c for c in checks if "INSUFFICIENT_DATA" in c.detail]
    if insufficient:
        warnings.append(
            f"{len(insufficient)} check(s) FAILED due to missing data: "
            + ", ".join(c.name for c in insufficient)
        )

    is_valid = all(c.passed for c in checks)

    logger.info(
        "mission_validation: mission_id=%s is_valid=%s passed=%d failed=%d",
        str(plan.mission_id),
        is_valid,
        sum(1 for c in checks if c.passed),
        sum(1 for c in checks if not c.passed),
    )

    return ValidationResult(
        is_valid=is_valid, checks=checks, warnings=warnings, violations=violations
    )
