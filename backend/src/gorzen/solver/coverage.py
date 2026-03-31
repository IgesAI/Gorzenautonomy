"""Coverage planning: built-in polygon-clipped lawnmower, optional drone-flightplan, OR-Tools TSP."""

from __future__ import annotations

import math
from typing import Any

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
    try:
        import geojson as _geojson
    except ImportError as e:
        raise RuntimeError(
            "geojson package required — pip install geojson or install gorzen[coverage]"
        ) from e

    fc = _geojson.loads(geojson_str)
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


def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    x, y = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi):
            inside = not inside
        j = i
    return inside


def _intersect_horizontal_line_with_polygon(
    lat: float,
    polygon: list[tuple[float, float]],
) -> list[float]:
    """Find all lon-intersections of a horizontal line at given lat with polygon edges."""
    intersections: list[float] = []
    n = len(polygon)
    for i in range(n):
        lat1, lon1 = polygon[i]
        lat2, lon2 = polygon[(i + 1) % n]
        if (lat1 <= lat < lat2) or (lat2 <= lat < lat1):
            if abs(lat2 - lat1) > 1e-15:
                lon_intersect = lon1 + (lat - lat1) * (lon2 - lon1) / (lat2 - lat1)
                intersections.append(lon_intersect)
    intersections.sort()
    return intersections


def generate_polygon_clipped_lawnmower(
    aoi: list[tuple[float, float]],
    altitude_m: float,
    gsd_params: dict[str, float],
    forward_overlap_pct: float = 70.0,
    side_overlap_pct: float = 65.0,
) -> list[tuple[float, float, float]]:
    """Generate polygon-clipped lawnmower survey waypoints.

    Uses scan-line intersection with the polygon boundary to produce
    waypoints that lie strictly inside the AOI. No external dependencies.
    Returns list of (lat, lon, altitude_m).
    """
    if len(aoi) < 3:
        return [(p[0], p[1], altitude_m) for p in aoi]

    sw = gsd_params.get("sensor_width_mm", 13.2)
    sh = gsd_params.get("sensor_height_mm", 8.8)
    fl = gsd_params.get("focal_length_mm", 24.0)
    px_w = gsd_params.get("pixel_width", 4000)
    px_h = gsd_params.get("pixel_height", 3000)

    gsd_w = sw * altitude_m / (fl * px_w)
    gsd_h = sh * altitude_m / (fl * px_h)
    footprint_w = gsd_w * px_w
    footprint_h = gsd_h * px_h

    line_spacing = footprint_w * (1.0 - side_overlap_pct / 100.0)
    along_spacing = footprint_h * (1.0 - forward_overlap_pct / 100.0)

    line_spacing = max(line_spacing, 0.5)
    along_spacing = max(along_spacing, 0.5)

    lats = [p[0] for p in aoi]
    lons = [p[1] for p in aoi]
    min_lat, max_lat = min(lats), max(lats)
    _min_lon, _max_lon = min(lons), max(lons)

    m_per_deg_lat = 111320.0
    center_lat = (min_lat + max_lat) / 2.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(center_lat))

    line_spacing / m_per_deg_lon if m_per_deg_lon > 0 else 1e-5
    along_spacing_deg = along_spacing / m_per_deg_lat

    polygon = list(aoi)
    if polygon[0] != polygon[-1]:
        polygon.append(polygon[0])

    waypoints: list[tuple[float, float, float]] = []
    lat = min_lat
    direction = 1
    while lat <= max_lat + along_spacing_deg:
        lon_crossings = _intersect_horizontal_line_with_polygon(lat, polygon)
        # Process crossing pairs: enter polygon at odd crossings, exit at even
        for k in range(0, len(lon_crossings) - 1, 2):
            seg_start_lon = lon_crossings[k]
            seg_end_lon = lon_crossings[k + 1]

            n_points = max(
                2, int(abs(seg_end_lon - seg_start_lon) * m_per_deg_lon / line_spacing) + 1
            )
            if direction == 1:
                lons_on_line = np.linspace(seg_start_lon, seg_end_lon, n_points)
            else:
                lons_on_line = np.linspace(seg_end_lon, seg_start_lon, n_points)
            for lon_pt in lons_on_line:
                waypoints.append((lat, float(lon_pt), altitude_m))

        lat += along_spacing_deg
        direction *= -1

    return waypoints


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
    routing.SetFirstSolutionStrategy(routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)  # type: ignore[attr-defined]

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
