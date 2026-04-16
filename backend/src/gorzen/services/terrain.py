"""Terrain elevation service using Open-Elevation API.

Provides ground elevation lookups from SRTM 30m data for AGL-to-MSL
conversion and terrain awareness. Phase 2c of the audit reworked this
module so the safety-critical terrain-clearance check can never silently
read "0 m above sea level" when the upstream API has nothing to say —
either it returns a concrete elevation or raises.

Reference: https://open-elevation.com/
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


OPEN_ELEVATION_URL = "https://api.open-elevation.com/api/v1/lookup"


class TerrainDataUnavailableError(RuntimeError):
    """The terrain API returned an empty / malformed response.

    Mission validators / path planners must treat this as a hard failure
    rather than reading the old ``elevation_m=0.0`` silent default — that
    default actively killed terrain-clearance checks for mountain routes.
    """


@dataclass
class TerrainPoint:
    """Elevation data for a single point."""

    latitude: float
    longitude: float
    elevation_m: float


@dataclass
class TerrainProfile:
    """Terrain elevation profile along a path."""

    points: list[TerrainPoint]
    min_elevation_m: float
    max_elevation_m: float
    mean_elevation_m: float
    elevation_range_m: float


async def fetch_elevation(lat: float, lon: float) -> TerrainPoint:
    """Fetch ground elevation for a single point.

    Raises :class:`TerrainDataUnavailableError` if the API returns no data
    or the response is missing required fields. Callers that need a safe
    fallback must handle the exception explicitly.
    """
    params = {"locations": f"{lat},{lon}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(OPEN_ELEVATION_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    if not results:
        raise TerrainDataUnavailableError(
            f"Open-Elevation returned no results for ({lat}, {lon})"
        )

    first = results[0]
    if "elevation" not in first:
        raise TerrainDataUnavailableError(
            f"Open-Elevation response missing 'elevation' field at ({lat}, {lon}): {first}"
        )

    return TerrainPoint(
        latitude=float(first.get("latitude", lat)),
        longitude=float(first.get("longitude", lon)),
        elevation_m=float(first["elevation"]),
    )


async def fetch_elevation_batch(
    points: list[tuple[float, float]],
) -> list[TerrainPoint]:
    """Fetch elevations for multiple points in one request.

    Raises :class:`TerrainDataUnavailableError` if the server does not
    return an elevation for every requested point — mountains silently
    becoming sea-level datapoints was the bug we were fixing.
    """
    if not points:
        return []

    locations = "|".join(f"{lat},{lon}" for lat, lon in points)
    params = {"locations": locations}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(OPEN_ELEVATION_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    if len(results) != len(points):
        raise TerrainDataUnavailableError(
            f"Open-Elevation returned {len(results)} results for {len(points)} requested points"
        )

    out: list[TerrainPoint] = []
    for i, r in enumerate(results):
        if "elevation" not in r:
            lat, lon = points[i]
            raise TerrainDataUnavailableError(
                f"Open-Elevation response missing elevation at point {i} ({lat}, {lon})"
            )
        out.append(
            TerrainPoint(
                latitude=float(r.get("latitude", points[i][0])),
                longitude=float(r.get("longitude", points[i][1])),
                elevation_m=float(r["elevation"]),
            )
        )
    return out


async def fetch_terrain_profile(
    points: list[tuple[float, float]],
) -> TerrainProfile:
    """Fetch terrain profile along a path of lat/lon points."""
    terrain_points = await fetch_elevation_batch(points)
    elevations = [p.elevation_m for p in terrain_points]

    if not elevations:
        # ``fetch_elevation_batch`` already raises on missing data for a
        # non-empty input; this branch handles the empty-input case where
        # the caller asked for zero points.
        return TerrainProfile(
            points=[],
            min_elevation_m=0,
            max_elevation_m=0,
            mean_elevation_m=0,
            elevation_range_m=0,
        )

    return TerrainProfile(
        points=terrain_points,
        min_elevation_m=min(elevations),
        max_elevation_m=max(elevations),
        mean_elevation_m=sum(elevations) / len(elevations),
        elevation_range_m=max(elevations) - min(elevations),
    )
