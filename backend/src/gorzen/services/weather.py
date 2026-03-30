"""Weather service client for Open-Meteo API.

Provides multi-altitude wind profiles, temperature, pressure, and
atmospheric conditions for drone flight planning.
Free API, no key required.

Reference: https://open-meteo.com/en/docs
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass
class WindLayer:
    """Wind conditions at a specific altitude."""
    height_m: float
    speed_ms: float
    direction_deg: float
    gusts_ms: float


@dataclass
class WeatherConditions:
    """Complete weather conditions for a location."""
    latitude: float
    longitude: float
    temperature_c: float
    pressure_hpa: float
    humidity_pct: float
    cloud_cover_pct: float
    visibility_m: float
    precipitation_mm: float
    wind_layers: list[WindLayer] = field(default_factory=list)
    density_altitude_ft: float = 0.0
    air_density_kgm3: float = 1.225
    flight_category: str = "VFR"  # VFR, MVFR, IFR, LIFR
    conditions_summary: str = ""
    timestamp: str = ""


def _classify_flight_category(vis_m: float, cloud_cover: float) -> str:
    """FAA flight category from visibility and cloud cover."""
    ceiling_ft = 99999 if cloud_cover < 70 else (3000 if cloud_cover < 90 else 1000)
    vis_sm = vis_m / 1609.34

    if vis_sm >= 5 and ceiling_ft >= 3000:
        return "VFR"
    elif vis_sm >= 3 and ceiling_ft >= 1000:
        return "MVFR"
    elif vis_sm >= 1 and ceiling_ft >= 500:
        return "IFR"
    else:
        return "LIFR"


def _compute_density_altitude(temp_c: float, pressure_hpa: float, elevation_m: float) -> float:
    """Compute density altitude in feet."""
    # ISA temperature at elevation
    isa_temp = 15.0 - 0.0065 * elevation_m
    pressure_alt_ft = (1 - (pressure_hpa / 1013.25) ** 0.190284) * 145366.45
    density_alt_ft = pressure_alt_ft + 120 * (temp_c - isa_temp)
    return density_alt_ft


def _compute_air_density(temp_c: float, pressure_hpa: float, humidity_pct: float) -> float:
    """Compute moist air density from ideal gas law with humidity correction."""
    T_k = temp_c + 273.15
    P_pa = pressure_hpa * 100.0
    # Saturation vapor pressure (Buck equation)
    e_sat = 611.21 * __import__('math').exp((18.678 - temp_c / 234.5) * (temp_c / (257.14 + temp_c)))
    e = e_sat * humidity_pct / 100.0
    # Virtual temperature
    Tv = T_k / (1 - 0.378 * e / P_pa)
    rho = P_pa / (287.058 * Tv)
    return rho


async def fetch_weather(
    lat: float,
    lon: float,
    elevation_m: float = 0.0,
) -> WeatherConditions:
    """Fetch current weather conditions from Open-Meteo.

    Returns multi-altitude wind profiles at 10m, 80m, 120m, 180m.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "surface_pressure",
            "cloud_cover",
            "visibility",
            "precipitation",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "wind_speed_80m",
            "wind_direction_80m",
            "wind_speed_120m",
            "wind_direction_120m",
            "wind_speed_180m",
            "wind_direction_180m",
        ]),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    current = data.get("current", {})

    temp_c = current.get("temperature_2m", 20.0)
    pressure = current.get("surface_pressure", 1013.25)
    humidity = current.get("relative_humidity_2m", 50.0)
    cloud_cover = current.get("cloud_cover", 0.0)
    visibility = current.get("visibility", 10000.0)
    precip = current.get("precipitation", 0.0)

    wind_layers = [
        WindLayer(
            height_m=10,
            speed_ms=current.get("wind_speed_10m", 0),
            direction_deg=current.get("wind_direction_10m", 0),
            gusts_ms=current.get("wind_gusts_10m", 0),
        ),
        WindLayer(
            height_m=80,
            speed_ms=current.get("wind_speed_80m", 0),
            direction_deg=current.get("wind_direction_80m", 0),
            gusts_ms=current.get("wind_speed_80m", 0) * 1.3,
        ),
        WindLayer(
            height_m=120,
            speed_ms=current.get("wind_speed_120m", 0),
            direction_deg=current.get("wind_direction_120m", 0),
            gusts_ms=current.get("wind_speed_120m", 0) * 1.3,
        ),
        WindLayer(
            height_m=180,
            speed_ms=current.get("wind_speed_180m", 0),
            direction_deg=current.get("wind_direction_180m", 0),
            gusts_ms=current.get("wind_speed_180m", 0) * 1.3,
        ),
    ]

    density_alt = _compute_density_altitude(temp_c, pressure, elevation_m)
    air_density = _compute_air_density(temp_c, pressure, humidity)
    flight_cat = _classify_flight_category(visibility, cloud_cover)

    # Summary
    if precip > 0:
        summary = "Precipitation"
    elif cloud_cover > 90:
        summary = "Overcast"
    elif cloud_cover > 50:
        summary = "Partly Cloudy"
    elif cloud_cover > 20:
        summary = "Mostly Clear"
    else:
        summary = "Clear"

    return WeatherConditions(
        latitude=lat,
        longitude=lon,
        temperature_c=round(temp_c, 1),
        pressure_hpa=round(pressure, 1),
        humidity_pct=round(humidity, 1),
        cloud_cover_pct=round(cloud_cover, 1),
        visibility_m=round(visibility, 0),
        precipitation_mm=round(precip, 1),
        wind_layers=wind_layers,
        density_altitude_ft=round(density_alt, 0),
        air_density_kgm3=round(air_density, 4),
        flight_category=flight_cat,
        conditions_summary=summary,
        timestamp=current.get("time", ""),
    )
