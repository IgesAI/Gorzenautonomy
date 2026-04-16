"""Phase 4 property test — Zermelo router never enters forbidden polygons.

Hypothesis generates random start/goal pairs and random obstacle rectangles
in a bounded lat/lon window. For any setup where a feasible route exists,
the router must never place a waypoint inside the forbidden region.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from gorzen.services.wind_field import (
    WindField3D,
    zermelo_time_optimal_route,
)


def _still_air_field(min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> WindField3D:
    lats = np.linspace(min_lat, max_lat, 5)
    lons = np.linspace(min_lon, max_lon, 5)
    alts = np.array([0.0, 100.0, 200.0])
    u = np.zeros((alts.size, lats.size, lons.size))
    v = np.zeros_like(u)
    w = np.zeros_like(u)
    return WindField3D(lats=lats, lons=lons, alts=alts, u=u, v=v, w=w)


@st.composite
def _scenario(draw: st.DrawFn) -> dict:
    min_lat = 36.9
    max_lat = 37.1
    min_lon = -122.1
    max_lon = -121.9
    start_lat = draw(st.floats(min_value=min_lat + 0.01, max_value=max_lat - 0.01))
    start_lon = draw(st.floats(min_value=min_lon + 0.01, max_value=max_lon - 0.01))
    # Keep goal at least 0.03° away so the router has to do work.
    goal_lat = draw(st.floats(min_value=min_lat + 0.01, max_value=max_lat - 0.01))
    goal_lon = draw(st.floats(min_value=min_lon + 0.01, max_value=max_lon - 0.01))
    # Sample a forbidden rectangle somewhere in the box.
    box_lat_min = draw(st.floats(min_value=min_lat, max_value=max_lat - 0.02))
    box_lat_max = box_lat_min + 0.01
    box_lon_min = draw(st.floats(min_value=min_lon, max_value=max_lon - 0.02))
    box_lon_max = box_lon_min + 0.01
    return {
        "start": (start_lat, start_lon),
        "goal": (goal_lat, goal_lon),
        "box": [
            (box_lat_min, box_lon_min),
            (box_lat_min, box_lon_max),
            (box_lat_max, box_lon_max),
            (box_lat_max, box_lon_min),
        ],
        "bbox": (min_lat, max_lat, min_lon, max_lon),
    }


from hypothesis import assume


@given(sc=_scenario())
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.filter_too_much],
)
def test_route_never_enters_forbidden_polygon(sc: dict) -> None:
    start = sc["start"]
    goal = sc["goal"]
    box = sc["box"]
    bbox = sc["bbox"]
    # Reject — not skip — degenerate scenarios so Hypothesis can search for
    # valid ones. ``assume`` tells the framework "this draw isn't useful"
    # without counting it against ``max_examples``.
    assume(not _point_in_box(start, box))
    assume(not _point_in_box(goal, box))
    assume(not _too_close(start, goal, 0.03))

    field = _still_air_field(*bbox)
    try:
        route = zermelo_time_optimal_route(
            start=start,
            goal=goal,
            wind=field,
            altitude_m=100.0,
            airspeed_ms=20.0,
            grid_size=15,
            buffer_deg=0.005,
            forbidden_polygons=[box],
        )
    except RuntimeError:
        # An entirely-blocked configuration is fine — the router is allowed
        # to refuse rather than invent a tunnelling path.
        return
    for wp in route:
        assert not _point_in_box((wp.latitude_deg, wp.longitude_deg), box), (
            f"Waypoint {wp} entered forbidden polygon {box}"
        )


def _point_in_box(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    """Strict interior inclusion (edges count as *outside*).

    The Zermelo router uses a ray-casting point-in-polygon whose edge
    semantics are "open": a grid node exactly on the boundary is not
    considered forbidden. Our property check must agree, otherwise an
    edge-touching waypoint would falsely flag as an escape.
    """
    lats = [p[0] for p in poly]
    lons = [p[1] for p in poly]
    return min(lats) < pt[0] < max(lats) and min(lons) < pt[1] < max(lons)


def _too_close(a: tuple[float, float], b: tuple[float, float], tol_deg: float) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) < tol_deg
