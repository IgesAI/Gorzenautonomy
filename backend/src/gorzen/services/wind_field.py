"""3D wind field + Zermelo-style time-optimal routing.

A ``WindField3D`` stores gridded wind vectors over (latitude, longitude,
altitude) bins and exposes a fast :meth:`WindField3D.at` lookup that
returns the wind components at any query point via trilinear interpolation.

Two routers are built on top:

* :func:`zermelo_time_optimal_route` — discretises a 2D lat/lon lane
  between start and goal at a fixed cruise altitude and solves the
  shortest-*time* path through the ground-speed field with an A\\* search.
  This is the classic Zermelo time-optimal navigation problem projected
  onto a regular graph, good enough for warm-starting the full 3D NLP.
* :func:`ground_speed_energy_cost` — helper that converts a planned
  airspeed + heading into the true ground-speed / energy cost, so the
  trajectory NLP can trade off time and energy consistently with real wind.

The field can be built from the existing :mod:`gorzen.services.weather`
layers (single forecast location, altitude-stratified) or from a larger
gridded product such as HRRR / ERA5 in future phases.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from gorzen.services.weather import WeatherConditions, WindLayer


EARTH_R = 6_371_000.0


@dataclass(frozen=True)
class WindVector:
    """Wind components in a local ENU frame. Signs follow the aviation
    convention: ``u_east`` positive toward geographic east, ``v_north``
    positive toward geographic north, ``w_up`` positive away from terrain.
    """

    u_east_ms: float
    v_north_ms: float
    w_up_ms: float = 0.0

    def speed(self) -> float:
        return math.hypot(self.u_east_ms, self.v_north_ms)

    def from_direction_deg(self) -> float:
        """Meteorological "from" direction (where wind is coming from)."""
        return (math.degrees(math.atan2(-self.u_east_ms, -self.v_north_ms)) + 360) % 360


@dataclass
class WindField3D:
    """Regular-grid wind field over (lat, lon, altitude).

    Attributes:
        lats, lons, alts: strictly-increasing 1-D arrays defining the grid.
        u, v, w: shape ``(len(alts), len(lats), len(lons))`` wind
            components in m/s (east / north / up).
        timestamp_iso: ISO-8601 timestamp of the forecast the grid was
            sampled from; used for downstream freshness checks.
    """

    lats: np.ndarray
    lons: np.ndarray
    alts: np.ndarray
    u: np.ndarray
    v: np.ndarray
    w: np.ndarray
    timestamp_iso: str = ""

    def __post_init__(self) -> None:
        for name in ("lats", "lons", "alts"):
            arr = getattr(self, name)
            if arr.ndim != 1 or arr.size < 2 or not np.all(np.diff(arr) > 0):
                raise ValueError(f"{name} must be 1-D strictly increasing (got shape {arr.shape})")
        expected = (self.alts.size, self.lats.size, self.lons.size)
        for name in ("u", "v", "w"):
            arr = getattr(self, name)
            if arr.shape != expected:
                raise ValueError(
                    f"{name} has shape {arr.shape}, expected {expected} (alts, lats, lons)"
                )

    # -- construction -------------------------------------------------------

    @classmethod
    def from_weather(
        cls,
        centre_lat: float,
        centre_lon: float,
        weather: WeatherConditions,
        horizontal_span_deg: float = 0.5,
        horizontal_cells: int = 5,
    ) -> "WindField3D":
        """Build a horizontally-uniform wind field from a single-point weather report.

        Useful as a zero-cost stand-in until a real gridded product is
        wired in. Every horizontal cell at a given altitude sees the same
        wind layer; altitude interpolation is between the forecast layers.
        """
        if not weather.wind_layers:
            raise ValueError("weather.wind_layers is empty; cannot build a wind field")
        layers = sorted(weather.wind_layers, key=lambda l: l.height_m)
        alts = np.array([l.height_m for l in layers], dtype=float)
        u_col = np.zeros(len(layers))
        v_col = np.zeros(len(layers))
        for i, layer in enumerate(layers):
            u_col[i], v_col[i] = _uv_from_speed_dir(layer.speed_ms, layer.direction_deg)

        half = horizontal_span_deg / 2.0
        lats = np.linspace(centre_lat - half, centre_lat + half, horizontal_cells)
        lons = np.linspace(centre_lon - half, centre_lon + half, horizontal_cells)
        u = np.broadcast_to(u_col[:, None, None], (alts.size, lats.size, lons.size)).copy()
        v = np.broadcast_to(v_col[:, None, None], (alts.size, lats.size, lons.size)).copy()
        w = np.zeros_like(u)
        return cls(lats=lats, lons=lons, alts=alts, u=u, v=v, w=w, timestamp_iso=weather.timestamp)

    # -- lookup -------------------------------------------------------------

    def at(self, lat: float, lon: float, altitude_m: float) -> WindVector:
        """Trilinear interpolation of (u, v, w) at the query point.

        Out-of-bounds queries clip to the nearest grid face — this is the
        safe choice for flight planning; callers that need strict bounds
        should check the enclosing box themselves.
        """
        la = _clip_interp_idx(self.lats, lat)
        lo = _clip_interp_idx(self.lons, lon)
        al = _clip_interp_idx(self.alts, altitude_m)
        u = _trilinear(self.u, al, la, lo)
        v = _trilinear(self.v, al, la, lo)
        w = _trilinear(self.w, al, la, lo)
        return WindVector(u_east_ms=float(u), v_north_ms=float(v), w_up_ms=float(w))


def _uv_from_speed_dir(speed: float, direction_deg: float) -> tuple[float, float]:
    """Meteorological (from-)direction → local ENU (u_east, v_north)."""
    rad = math.radians(direction_deg)
    # Meteorological direction is the *source* direction; the wind vector
    # points 180° the other way.
    u = -speed * math.sin(rad)
    v = -speed * math.cos(rad)
    return u, v


def _clip_interp_idx(axis: np.ndarray, value: float) -> tuple[int, int, float]:
    """Return (i0, i1, t) with value ≈ axis[i0] + t*(axis[i1]-axis[i0])."""
    if value <= axis[0]:
        return 0, 0, 0.0
    if value >= axis[-1]:
        n = len(axis) - 1
        return n, n, 0.0
    i1 = int(np.searchsorted(axis, value))
    i0 = i1 - 1
    span = axis[i1] - axis[i0]
    t = 0.0 if span == 0 else (value - axis[i0]) / span
    return i0, i1, float(t)


def _trilinear(
    arr: np.ndarray,
    al: tuple[int, int, float],
    la: tuple[int, int, float],
    lo: tuple[int, int, float],
) -> float:
    a0, a1, ta = al
    y0, y1, ty = la
    x0, x1, tx = lo
    c000 = arr[a0, y0, x0]
    c001 = arr[a0, y0, x1]
    c010 = arr[a0, y1, x0]
    c011 = arr[a0, y1, x1]
    c100 = arr[a1, y0, x0]
    c101 = arr[a1, y0, x1]
    c110 = arr[a1, y1, x0]
    c111 = arr[a1, y1, x1]
    c00 = c000 * (1 - tx) + c001 * tx
    c01 = c010 * (1 - tx) + c011 * tx
    c10 = c100 * (1 - tx) + c101 * tx
    c11 = c110 * (1 - tx) + c111 * tx
    c0 = c00 * (1 - ty) + c01 * ty
    c1 = c10 * (1 - ty) + c11 * ty
    return c0 * (1 - ta) + c1 * ta


# ---------------------------------------------------------------------------
# Wind-triangle helpers
# ---------------------------------------------------------------------------


def ground_speed_from_airspeed(
    airspeed_ms: float, heading_deg: float, wind: WindVector
) -> tuple[float, float, float]:
    """Given airspeed + heading, return (ground_speed, track_deg, ground_course_deg).

    Heading is where the nose points (degrees from north, clockwise);
    ``track`` is the resulting ground track. A tailwind increases ground
    speed; a crosswind rotates the track away from the heading.
    """
    rad = math.radians(heading_deg)
    air_u = airspeed_ms * math.sin(rad)
    air_v = airspeed_ms * math.cos(rad)
    gnd_u = air_u + wind.u_east_ms
    gnd_v = air_v + wind.v_north_ms
    gs = math.hypot(gnd_u, gnd_v)
    track = (math.degrees(math.atan2(gnd_u, gnd_v)) + 360) % 360
    return gs, track, track


def heading_for_track(
    airspeed_ms: float,
    desired_track_deg: float,
    wind: WindVector,
) -> tuple[float, float]:
    """Solve the wind triangle for the heading that yields ``desired_track``.

    Returns ``(heading_deg, ground_speed_ms)``. Raises :class:`ValueError`
    when the wind is stronger than the airspeed and no heading can achieve
    the track (the aircraft is wind-bound).
    """
    tw = math.radians(desired_track_deg)
    # Wind component along (tailwind) and perpendicular to (crosswind) the track.
    track_u = math.sin(tw)
    track_v = math.cos(tw)
    tailwind = wind.u_east_ms * track_u + wind.v_north_ms * track_v
    crosswind = wind.u_east_ms * track_v - wind.v_north_ms * track_u

    if abs(crosswind) > airspeed_ms:
        raise ValueError(
            "Wind is too strong to hold the desired track at this airspeed "
            f"(|crosswind|={abs(crosswind):.1f} > airspeed={airspeed_ms:.1f})"
        )
    wca = math.asin(crosswind / airspeed_ms)  # wind correction angle
    heading = (desired_track_deg + math.degrees(wca)) % 360
    gs = airspeed_ms * math.cos(wca) + tailwind
    if gs <= 0:
        raise ValueError(
            "Wind exceeds airspeed along track; aircraft cannot make progress"
        )
    return float(heading), float(gs)


def ground_speed_energy_cost(
    airspeed_ms: float,
    desired_track_deg: float,
    wind: WindVector,
    power_fn: Callable[[float, float], float],
    altitude_m: float,
    segment_length_m: float,
) -> tuple[float, float]:
    """Return ``(duration_s, energy_Wh)`` for flying ``segment_length_m``
    along ``desired_track_deg`` at ``airspeed_ms`` through ``wind``.

    The caller's ``power_fn(airspeed, altitude)`` is evaluated at the
    chosen airspeed (power is a function of airspeed, not ground speed —
    drag acts on the air, not the earth).
    """
    _, gs = heading_for_track(airspeed_ms, desired_track_deg, wind)
    duration_s = segment_length_m / max(gs, 1e-3)
    power_w = power_fn(airspeed_ms, altitude_m)
    energy_wh = power_w * duration_s / 3600.0
    return duration_s, energy_wh


# ---------------------------------------------------------------------------
# Zermelo-style time-optimal A* on a lat/lon grid
# ---------------------------------------------------------------------------


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return EARTH_R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(rlat2)
    y = math.cos(rlat1) * math.sin(rlat2) - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


@dataclass
class ZermeloWaypoint:
    """Output of the Zermelo router."""

    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    airspeed_ms: float
    heading_deg: float
    ground_speed_ms: float
    cumulative_time_s: float


def zermelo_time_optimal_route(
    start: tuple[float, float],
    goal: tuple[float, float],
    wind: WindField3D,
    altitude_m: float,
    airspeed_ms: float,
    grid_size: int = 25,
    buffer_deg: float = 0.02,
    forbidden_polygons: list[list[tuple[float, float]]] | None = None,
) -> list[ZermeloWaypoint]:
    """Compute a minimum-time route through ``wind`` between ``start`` and ``goal``.

    Builds a regular lat/lon graph covering the bounding box of the two
    endpoints (inflated by ``buffer_deg``) and runs A\\* with the edge cost
    equal to ``segment_length / ground_speed``. Forbidden polygons (e.g.
    controlled airspace from Phase 3c) are excluded from the graph.

    Returns a list of :class:`ZermeloWaypoint` ordered from start to goal.
    Raises :class:`RuntimeError` if no feasible route exists.
    """
    if forbidden_polygons is None:
        forbidden_polygons = []

    la_min = min(start[0], goal[0]) - buffer_deg
    la_max = max(start[0], goal[0]) + buffer_deg
    lo_min = min(start[1], goal[1]) - buffer_deg
    lo_max = max(start[1], goal[1]) + buffer_deg
    lats = np.linspace(la_min, la_max, grid_size)
    lons = np.linspace(lo_min, lo_max, grid_size)

    start_idx = (_nearest_idx(lats, start[0]), _nearest_idx(lons, start[1]))
    goal_idx = (_nearest_idx(lats, goal[0]), _nearest_idx(lons, goal[1]))

    # A* heuristic: straight-line distance / (airspeed + max_tailwind) is
    # guaranteed admissible (never overestimates) when the max tailwind we
    # ever see is the field's worst-case speed.
    max_tailwind = float(
        np.max(np.sqrt(wind.u * wind.u + wind.v * wind.v))
    )
    reference_speed = max(airspeed_ms + max_tailwind, 1e-3)

    def _heuristic(i: int, j: int) -> float:
        la = lats[i]
        lo = lons[j]
        return _haversine_m(la, lo, goal[0], goal[1]) / reference_speed

    def _in_forbidden(la: float, lo: float) -> bool:
        for poly in forbidden_polygons:
            if _point_in_polygon(la, lo, poly):
                return True
        return False

    # 8-neighbour connectivity.
    neighbours = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    gscore: dict[tuple[int, int], float] = {start_idx: 0.0}
    came: dict[tuple[int, int], tuple[int, int]] = {}
    came_leg: dict[tuple[int, int], tuple[float, float, float]] = {}
    open_heap: list[tuple[float, tuple[int, int]]] = [(_heuristic(*start_idx), start_idx)]

    while open_heap:
        _, (i, j) = heapq.heappop(open_heap)
        if (i, j) == goal_idx:
            break
        for di, dj in neighbours:
            ni, nj = i + di, j + dj
            if not (0 <= ni < grid_size and 0 <= nj < grid_size):
                continue
            la_n = lats[ni]
            lo_n = lons[nj]
            if _in_forbidden(la_n, lo_n):
                continue
            la_c = lats[i]
            lo_c = lons[j]
            seg_m = _haversine_m(la_c, lo_c, la_n, lo_n)
            if seg_m == 0:
                continue
            track = _initial_bearing_deg(la_c, lo_c, la_n, lo_n)
            # Evaluate wind at the midpoint of the edge (good enough for
            # this coarse A\* warm start; the NLP will refine).
            mid_lat = 0.5 * (la_c + la_n)
            mid_lon = 0.5 * (lo_c + lo_n)
            w = wind.at(mid_lat, mid_lon, altitude_m)
            try:
                heading, gs = heading_for_track(airspeed_ms, track, w)
            except ValueError:
                # Wind too strong for this edge — skip.
                continue
            edge_cost = seg_m / max(gs, 1e-3)
            tentative = gscore[(i, j)] + edge_cost
            if tentative < gscore.get((ni, nj), math.inf):
                gscore[(ni, nj)] = tentative
                came[(ni, nj)] = (i, j)
                came_leg[(ni, nj)] = (heading, gs, edge_cost)
                fscore = tentative + _heuristic(ni, nj)
                heapq.heappush(open_heap, (fscore, (ni, nj)))

    if goal_idx not in gscore:
        raise RuntimeError(
            "No feasible Zermelo route (wind too strong, or forbidden polygons block every path)"
        )

    # Reconstruct.
    path: list[tuple[int, int]] = []
    cur = goal_idx
    while cur in came:
        path.append(cur)
        cur = came[cur]
    path.append(start_idx)
    path.reverse()

    waypoints: list[ZermeloWaypoint] = []
    cum_t = 0.0
    for n, (i, j) in enumerate(path):
        if n == 0:
            heading = _initial_bearing_deg(lats[i], lons[j], goal[0], goal[1])
            gs = airspeed_ms
        else:
            heading, gs, edge_cost = came_leg[(i, j)]
            cum_t += edge_cost
        waypoints.append(
            ZermeloWaypoint(
                latitude_deg=float(lats[i]),
                longitude_deg=float(lons[j]),
                altitude_m=float(altitude_m),
                airspeed_ms=float(airspeed_ms),
                heading_deg=float(heading),
                ground_speed_ms=float(gs),
                cumulative_time_s=float(cum_t),
            )
        )
    return waypoints


def _nearest_idx(axis: np.ndarray, value: float) -> int:
    return int(np.argmin(np.abs(axis - value)))


def _point_in_polygon(lat: float, lon: float, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if (yi > lat) != (yj > lat):
            x_intersect = (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi
            if lon < x_intersect:
                inside = not inside
        j = i
    return inside


__all__ = [
    "WindField3D",
    "WindVector",
    "WindLayer",
    "ZermeloWaypoint",
    "ground_speed_energy_cost",
    "ground_speed_from_airspeed",
    "heading_for_track",
    "zermelo_time_optimal_route",
]
