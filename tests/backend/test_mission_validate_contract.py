"""Contract tests: mission_validator kwargs align with /mission-plan/validate body."""

from __future__ import annotations

from gorzen.schemas.mission import MissionPlan, Waypoint, WaypointType
from gorzen.services.mission_validator import validate_mission


def _two_wp_plan() -> MissionPlan:
    wps = [
        Waypoint(
            sequence=0,
            wp_type=WaypointType.TAKEOFF,
            latitude_deg=35.0,
            longitude_deg=-106.6,
            altitude_m=100.0,
            speed_ms=15.0,
        ),
        Waypoint(
            sequence=1,
            wp_type=WaypointType.NAVIGATE,
            latitude_deg=35.001,
            longitude_deg=-106.6,
            altitude_m=100.0,
            speed_ms=15.0,
        ),
    ]
    return MissionPlan(
        twin_id="test",
        waypoints=wps,
        estimated_duration_s=60.0,
        estimated_distance_m=100.0,
        estimated_energy_wh=100.0,
    )


def _twin() -> dict:
    return {
        "max_speed_ms": 30.0,
        "endurance_min": 45.0,
        "wind_limit_ms": 12.0,
        "operating_temp_min_c": -10.0,
        "operating_temp_max_c": 45.0,
        "payload_max_kg": 5.0,
        "sensor_width_mm": 13.2,
        "sensor_height_mm": 8.8,
        "focal_length_mm": 24.0,
        "pixel_width": 4000.0,
        "pixel_height": 3000.0,
        "energy_capacity_wh": 50000.0,
    }


def _common_geo() -> tuple[list[tuple[float, float]], list[float]]:
    """Rectangle containing both waypoints; terrain MSL below waypoint alt for AGL."""
    gf = [
        (34.99, -106.65),
        (35.02, -106.65),
        (35.02, -106.55),
        (34.99, -106.55),
    ]
    terrain = [50.0, 50.0]
    return gf, terrain


def test_detection_insufficient_without_target_size() -> None:
    gf, terrain = _common_geo()
    plan = _two_wp_plan()
    res = validate_mission(
        plan,
        _twin(),
        environment={"wind_speed_ms": 5.0, "temperature_c": 15.0},
        geofence=gf,
        terrain_elevations_m=terrain,
        required_payload_kg=2.0,
    )
    det = next(c for c in res.checks if c.name == "detection_capability")
    assert "INSUFFICIENT_DATA" in det.detail


def test_perception_kwargs_remove_insufficient_for_core_checks() -> None:
    gf, terrain = _common_geo()
    plan = _two_wp_plan()
    res = validate_mission(
        plan,
        _twin(),
        environment={"wind_speed_ms": 5.0, "temperature_c": 15.0},
        geofence=gf,
        terrain_elevations_m=terrain,
        required_payload_kg=2.0,
        target_size_m=0.5,
        min_pixels_on_target=10.0,
        max_gsd_cm_px=2.5,
        exposure_time_s=0.002,
        max_blur_px=1.0,
        min_overlap_pct=60.0,
        trigger_interval_m=25.0,
    )
    for name in ("detection_capability", "gsd", "motion_blur", "frame_overlap"):
        c = next(x for x in res.checks if x.name == name)
        assert "INSUFFICIENT_DATA" not in c.detail, (name, c.detail)
