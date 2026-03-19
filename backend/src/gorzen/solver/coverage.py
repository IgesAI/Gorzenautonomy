"""Coverage planning: drone-flightplan integration and OR-Tools route optimization."""

from __future__ import annotations

import math
from typing import Any

import geojson
import numpy as np

try:
    from drone_flightplan import create_waypoint
    HAS_DRONE_FLIGHTPLAN = True
except ImportError:
    HAS_DRONE_FLIGHTPLAN = False

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False


def aoi_to_geojson(aoi: list[tuple[float, float]]) -> dict[str, Any]:
    """Convert [(lat, lon), ...] to GeoJSON FeatureCollection polygon."""
    if len(aoi) < 3:
        return {"type": "FeatureCollection", "features": []}
    coords = [[lon, lat] for lat, lon in aoi]
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords]}}],
    }


def geojson_to_waypoints(
    geojson_str: str,
    altitude_m: float,
    take_off: tuple[float, float] | None = None,
) -> list[tuple[float, float, float]]:
    """Parse drone-flightplan GeoJSON output to (lat, lon, alt) waypoints."""
    fc = geojson.loads(geojson_str)
    waypoints: list[tuple[float, float, float]] = []
    for f in fc.get("features", []):
        geom = f.get("geometry")
        if not geom or geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates", [])
        if len(coords) >= 2:
            lon, lat = coords[0], coords[1]
            waypoints.append((lat, lon, altitude_m))
    return waypoints


def generate_coverage_waypoints_drone_flightplan(
    aoi: list[tuple[float, float]],
    altitude_m: float,
    gsd_cm_px: float,
    forward_overlap_pct: float = 70.0,
    side_overlap_pct: float = 65.0,
    rotation_deg: float = 0.0,
    take_off: tuple[float, float] | None = None,
    mode: str = "waylines",
) -> list[tuple[float, float, float]]:
    """Generate coverage waypoints using drone-flightplan (HOT OSM).

    Returns list of (lat, lon, altitude_m).
    """
    if not HAS_DRONE_FLIGHTPLAN:
        return []

    project_area = aoi_to_geojson(aoi)
    take_off_list = [take_off[1], take_off[0]] if take_off else None  # [lon, lat]

    geojson_str = create_waypoint(
        project_area,
        altitude_m,
        gsd_cm_px,
        forward_overlap_pct,
        side_overlap_pct,
        rotation_angle=rotation_deg,
        generate_3d=False,
        no_fly_zones=None,
        take_off_point=take_off_list,
        mode=mode,
    )
    return geojson_to_waypoints(geojson_str, altitude_m, take_off)


def optimize_waypoint_order_ortools(
    waypoints: list[tuple[float, float]],
    depot: tuple[float, float] | None = None,
) -> list[int]:
    """Use OR-Tools TSP to optimize waypoint visit order (minimize total distance).

    Returns permutation of indices [0..n-1].
    """
    if not HAS_ORTOOLS or len(waypoints) < 2:
        return list(range(len(waypoints)))

    n = len(waypoints)
    depot_idx = 0
    if depot is not None:
        depot_idx = min(
            range(n),
            key=lambda i: _haversine_m(depot, waypoints[i]),
        )

    def dist(i: int, j: int) -> int:
        return int(_haversine_m(waypoints[i], waypoints[j]) * 1000)

    manager = pywrapcp.RoutingIndexManager(n, 1, depot_idx)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_idx: int, to_idx: int) -> int:
        from_node = manager.IndexToNode(from_idx)
        to_node = manager.IndexToNode(to_idx)
        return dist(from_node, to_node)

    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(distance_callback))
    routing.SetFirstSolutionStrategy(routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)

    solution = routing.Solve()
    if not solution:
        return list(range(len(waypoints)))

    order: list[int] = []
    idx = routing.Start(0)
    while not routing.IsEnd(idx):
        order.append(manager.IndexToNode(idx))
        idx = solution.Value(routing.NextVar(idx))
    return order


def _haversine_m(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    R = 6371000
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
