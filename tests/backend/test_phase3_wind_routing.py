"""Phase 3a regression tests — 3D wind field + Zermelo routing."""

from __future__ import annotations

import math

import numpy as np
import pytest

from gorzen.services.weather import WeatherConditions, WindLayer
from gorzen.services.wind_field import (
    WindField3D,
    WindVector,
    ground_speed_energy_cost,
    ground_speed_from_airspeed,
    heading_for_track,
    zermelo_time_optimal_route,
)


def _demo_field(u: float, v: float, alt: float = 100.0) -> WindField3D:
    lats = np.linspace(36.99, 37.05, 5)
    lons = np.linspace(-122.05, -121.99, 5)
    alts = np.array([0.0, alt, alt * 2.0])
    u_arr = np.full((alts.size, lats.size, lons.size), u)
    v_arr = np.full((alts.size, lats.size, lons.size), v)
    w_arr = np.zeros_like(u_arr)
    return WindField3D(lats=lats, lons=lons, alts=alts, u=u_arr, v=v_arr, w=w_arr)


class TestWindField:
    def test_from_weather_builds_uniform_field(self) -> None:
        weather = WeatherConditions(
            latitude=37.0,
            longitude=-122.0,
            temperature_c=15.0,
            pressure_hpa=1013.0,
            humidity_pct=50.0,
            cloud_cover_pct=20.0,
            visibility_m=10_000.0,
            precipitation_mm=0.0,
            wind_layers=[
                WindLayer(height_m=10.0, speed_ms=5.0, direction_deg=270.0, gusts_ms=7.0),
                WindLayer(height_m=100.0, speed_ms=10.0, direction_deg=270.0, gusts_ms=float("nan")),
            ],
        )
        field = WindField3D.from_weather(37.0, -122.0, weather)
        assert field.u.shape[0] == 2  # two altitude layers
        wv = field.at(37.0, -122.0, 100.0)
        # Wind FROM 270° means blowing TO 90° (east): u_east > 0.
        assert wv.u_east_ms > 0.0
        assert abs(wv.v_north_ms) < 1e-6


class TestWindTriangle:
    def test_heading_for_track_matches_still_air(self) -> None:
        wind = WindVector(0.0, 0.0, 0.0)
        hd, gs = heading_for_track(20.0, 90.0, wind)
        assert hd == pytest.approx(90.0)
        assert gs == pytest.approx(20.0)

    def test_tailwind_increases_ground_speed(self) -> None:
        # Wind toward east at 5 m/s; flying east at 20 m/s airspeed -> 25 m/s GS.
        wind = WindVector(5.0, 0.0, 0.0)
        _, gs = heading_for_track(20.0, 90.0, wind)
        assert gs == pytest.approx(25.0, rel=1e-6)

    def test_crosswind_rotates_heading(self) -> None:
        # Flying a ground track of due east (90°) while the wind is pushing
        # the aircraft north (v_north > 0 i.e. southerly wind). To hold
        # track we crab to the south -> heading < 90° (pointing SE).
        wind = WindVector(0.0, 5.0, 0.0)
        hd, gs = heading_for_track(20.0, 90.0, wind)
        assert hd < 90.0
        assert hd > 0.0
        assert gs > 0.0

    def test_wind_stronger_than_airspeed_raises(self) -> None:
        wind = WindVector(50.0, 0.0, 0.0)
        with pytest.raises(ValueError):
            heading_for_track(10.0, 0.0, wind)

    def test_ground_speed_energy_cost_tailwind_cheaper(self) -> None:
        power_fn = lambda v, h: 500.0  # noqa: E731 — constant power for test
        tail = WindVector(5.0, 0.0, 0.0)
        head = WindVector(-5.0, 0.0, 0.0)
        dur_tail, en_tail = ground_speed_energy_cost(20.0, 90.0, tail, power_fn, 100.0, 1000.0)
        dur_head, en_head = ground_speed_energy_cost(20.0, 90.0, head, power_fn, 100.0, 1000.0)
        assert dur_tail < dur_head
        assert en_tail < en_head


class TestZermeloRouter:
    def test_route_reaches_goal_in_calm(self) -> None:
        field = _demo_field(u=0.0, v=0.0)
        route = zermelo_time_optimal_route(
            start=(37.0, -122.0),
            goal=(37.03, -122.01),
            wind=field,
            altitude_m=100.0,
            airspeed_ms=20.0,
            grid_size=10,
        )
        assert len(route) >= 2
        assert route[-1].latitude_deg == pytest.approx(37.03, abs=0.01)

    def test_tailwind_route_faster_than_headwind(self) -> None:
        # Route flying mostly east. Eastward wind should shorten cumulative time.
        tailwind = _demo_field(u=5.0, v=0.0)
        headwind = _demo_field(u=-5.0, v=0.0)
        start, goal = (37.0, -122.04), (37.0, -122.00)
        route_tail = zermelo_time_optimal_route(
            start, goal, tailwind, altitude_m=100.0, airspeed_ms=15.0, grid_size=12
        )
        route_head = zermelo_time_optimal_route(
            start, goal, headwind, altitude_m=100.0, airspeed_ms=15.0, grid_size=12
        )
        assert route_tail[-1].cumulative_time_s < route_head[-1].cumulative_time_s

    def test_forbidden_polygon_avoided(self) -> None:
        field = _demo_field(u=0.0, v=0.0)
        # Box that sits directly on a straight-line path between endpoints.
        block = [(37.01, -122.03), (37.01, -122.02), (37.02, -122.02), (37.02, -122.03)]
        route = zermelo_time_optimal_route(
            start=(37.0, -122.04),
            goal=(37.03, -122.00),
            wind=field,
            altitude_m=100.0,
            airspeed_ms=20.0,
            grid_size=20,
            forbidden_polygons=[block],
        )
        for wp in route:
            # Every waypoint must be outside the forbidden polygon.
            assert not (
                37.01 < wp.latitude_deg < 37.02 and -122.03 < wp.longitude_deg < -122.02
            )


class TestGroundSpeedSign:
    def test_still_air_round_trip(self) -> None:
        wind = WindVector(0.0, 0.0, 0.0)
        gs, _, _ = ground_speed_from_airspeed(20.0, 45.0, wind)
        assert gs == pytest.approx(20.0)

    def test_angular_conversion(self) -> None:
        wind = WindVector(0.0, 0.0, 0.0)
        gs, track, course = ground_speed_from_airspeed(15.0, 37.0, wind)
        assert math.isclose(track, 37.0, abs_tol=1e-6)
        assert course == track
