"""Terrain elevation service using Open-Elevation API.

Provides ground elevation lookups from SRTM 30m data for
AGL-to-MSL conversion and terrain awareness.

Reference: https://open-elevation.com/
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


OPEN_ELEVATION_URL = "https://api.open-elevation.com/api/v1/lookup"


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
    """Fetch ground elevation for a single point."""
    params = {"locations": f"{lat},{lon}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(OPEN_ELEVATION_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    if not results:
        return TerrainPoint(latitude=lat, longitude=lon, elevation_m=0.0)

    return TerrainPoint(
        latitude=results[0].get("latitude", lat),
        longitude=results[0].get("longitude", lon),
        elevation_m=results[0].get("elevation", 0.0),
    )


async def fetch_elevation_batch(
    points: list[tuple[float, float]],
) -> list[TerrainPoint]:
    """Fetch elevations for multiple points in one request."""
    if not points:
        return []

    locations = "|".join(f"{lat},{lon}" for lat, lon in points)
    params = {"locations": locations}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(OPEN_ELEVATION_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    return [
        TerrainPoint(
            latitude=r.get("latitude", 0),
            longitude=r.get("longitude", 0),
            elevation_m=r.get("elevation", 0),
        )
        for r in results
    ]


async def fetch_terrain_profile(
    points: list[tuple[float, float]],
) -> TerrainProfile:
    """Fetch terrain profile along a path of lat/lon points."""
    terrain_points = await fetch_elevation_batch(points)
    elevations = [p.elevation_m for p in terrain_points]

    if not elevations:
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
