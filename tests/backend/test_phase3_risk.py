"""Phase 3d regression tests — ground-risk model."""

from __future__ import annotations

import pytest

from gorzen.schemas.mission import MissionPlan, Waypoint, WaypointType
from gorzen.services.risk import (
    CrashConeModel,
    SoraGrc,
    assess_mission_risk,
    uniform_density_raster,
)


def _plan(alts: list[float] | None = None) -> MissionPlan:
    alts = alts or [50.0, 100.0, 80.0]
    wps = [
        Waypoint(
            sequence=i,
            wp_type=WaypointType.NAVIGATE,
            latitude_deg=37.0 + 0.01 * i,
            longitude_deg=-122.0 - 0.01 * i,
            altitude_m=a,
        )
        for i, a in enumerate(alts)
    ]
    return MissionPlan(twin_id="t", waypoints=wps, estimated_duration_s=120.0)


class TestCrashCone:
    def test_impact_radius_grows_with_altitude(self) -> None:
        cone = CrashConeModel()
        r_low = cone.impact_radius_m(50.0, 20.0)
        r_high = cone.impact_radius_m(500.0, 20.0)
        assert r_high > r_low

    def test_sample_returns_2d_array(self) -> None:
        cone = CrashConeModel()
        pts = cone.sample_impact_points(centre=(37.0, -122.0), altitude_agl_m=100.0, airspeed_ms=15.0, n_samples=50)
        assert pts.shape == (50, 2)


class TestAssessMissionRisk:
    def test_rural_low_grc(self) -> None:
        plan = _plan()
        raster = uniform_density_raster(1.0)  # ~Class GRC_2
        result = assess_mission_risk(
            plan,
            population=raster,
            cone=CrashConeModel(),
            cruise_airspeed_ms=18.0,
            failure_rate_per_hour=1e-3,
        )
        assert result.grc.value <= SoraGrc.GRC_2.value
        assert result.expected_fatalities_per_hour < 1e-5

    def test_urban_high_grc(self) -> None:
        plan = _plan()
        raster = uniform_density_raster(5_000.0)  # dense urban
        result = assess_mission_risk(
            plan,
            population=raster,
            cone=CrashConeModel(),
            cruise_airspeed_ms=18.0,
            failure_rate_per_hour=1e-3,
        )
        assert result.grc.value >= SoraGrc.GRC_5.value
        assert not result.acceptable(SoraGrc.GRC_4)

    def test_empty_mission_raises(self) -> None:
        plan = MissionPlan(twin_id="empty", waypoints=[])
        with pytest.raises(ValueError):
            assess_mission_risk(
                plan,
                population=uniform_density_raster(10.0),
                cone=CrashConeModel(),
                cruise_airspeed_ms=15.0,
            )

    def test_details_reported_per_leg(self) -> None:
        plan = _plan()
        result = assess_mission_risk(
            plan,
            population=uniform_density_raster(250.0),
            cone=CrashConeModel(),
            cruise_airspeed_ms=15.0,
        )
        assert len(result.details_by_waypoint) == len(plan.waypoints) - 1
        for d in result.details_by_waypoint:
            assert "leg_distance_m" in d
            assert "mean_density_ppkm2" in d
            assert d["mean_density_ppkm2"] == pytest.approx(250.0, rel=1e-6)
