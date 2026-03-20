"""Solar position and irradiance model.

Computes sun position, clear-sky irradiance, and scene illuminance (lux)
from latitude, longitude, and UTC datetime using analytical formulas.
No external dependencies beyond numpy.

References:
- Meeus, "Astronomical Algorithms", Willmann-Bell, 1998
- Spencer, "Fourier series representation of the position of the sun", 1971
- Ineichen & Perez, "A new airmass independent formulation for the Linke
  turbidity coefficient", Solar Energy 73(3), 2002
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class SolarPosition:
    """Sun position and derived illuminance quantities."""
    elevation_deg: float
    azimuth_deg: float
    zenith_deg: float
    hour_angle_deg: float
    declination_deg: float
    sunrise_hour: float
    sunset_hour: float
    day_length_hr: float
    ghi_w_m2: float        # Global Horizontal Irradiance
    dni_w_m2: float        # Direct Normal Irradiance
    dhi_w_m2: float        # Diffuse Horizontal Irradiance
    illuminance_lux: float  # Scene illuminance estimate
    solar_noon_utc: str
    is_daytime: bool


def _julian_day(dt: datetime) -> float:
    """Julian Day Number from UTC datetime."""
    y = dt.year
    m = dt.month
    d = dt.day + (dt.hour + dt.minute / 60.0 + dt.second / 3600.0) / 24.0
    if m <= 2:
        y -= 1
        m += 12
    A = int(y / 100)
    B = 2 - A + int(A / 4)
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + B - 1524.5


def compute_solar_position(
    lat: float,
    lon: float,
    dt: datetime | None = None,
    altitude_m: float = 0.0,
    linke_turbidity: float = 3.0,
) -> SolarPosition:
    """Compute solar position and clear-sky irradiance.

    Args:
        lat: Latitude in degrees (-90 to 90)
        lon: Longitude in degrees (-180 to 180)
        dt: UTC datetime (defaults to now)
        altitude_m: Site altitude in meters (for air mass correction)
        linke_turbidity: Linke turbidity factor (2=very clear, 3=clear, 5=hazy)
    """
    if dt is None:
        dt = datetime.now(timezone.utc)

    jd = _julian_day(dt)
    n = jd - 2451545.0  # days since J2000.0

    # Solar mean longitude and anomaly (degrees)
    L0 = (280.46646 + 0.9856474 * n) % 360
    M = math.radians((357.52911 + 0.9856003 * n) % 360)

    # Equation of center
    C = 1.9146 * math.sin(M) + 0.02 * math.sin(2 * M)
    sun_lon = math.radians(L0 + C)

    # Obliquity of ecliptic
    obliquity = math.radians(23.439 - 0.0000004 * n)

    # Declination
    declination = math.asin(math.sin(obliquity) * math.sin(sun_lon))
    dec_deg = math.degrees(declination)

    # Equation of time (minutes)
    B = math.radians((360 / 365) * (n - 81))
    eot = 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)

    # Solar time
    solar_time_min = (
        dt.hour * 60 + dt.minute + dt.second / 60.0 + lon * 4 + eot
    )
    hour_angle = (solar_time_min / 4.0 - 180.0)
    ha_rad = math.radians(hour_angle)

    # Solar elevation and azimuth
    lat_rad = math.radians(lat)
    sin_elev = (
        math.sin(lat_rad) * math.sin(declination)
        + math.cos(lat_rad) * math.cos(declination) * math.cos(ha_rad)
    )
    elevation = math.asin(max(-1, min(1, sin_elev)))
    elev_deg = math.degrees(elevation)
    zenith_deg = 90.0 - elev_deg

    # Azimuth
    cos_az = (
        (math.sin(declination) - math.sin(lat_rad) * sin_elev)
        / (math.cos(lat_rad) * math.cos(elevation) + 1e-12)
    )
    cos_az = max(-1, min(1, cos_az))
    azimuth = math.degrees(math.acos(cos_az))
    if hour_angle > 0:
        azimuth = 360.0 - azimuth

    # Sunrise/sunset hour angle
    cos_ws = -math.tan(lat_rad) * math.tan(declination)
    if cos_ws < -1:
        # Midnight sun
        sunrise_h, sunset_h, day_len = 0.0, 24.0, 24.0
    elif cos_ws > 1:
        # Polar night
        sunrise_h, sunset_h, day_len = 12.0, 12.0, 0.0
    else:
        ws = math.degrees(math.acos(cos_ws))
        day_len = 2.0 * ws / 15.0
        solar_noon_h = 12.0 - (lon * 4 + eot) / 60.0
        sunrise_h = solar_noon_h - day_len / 2.0
        sunset_h = solar_noon_h + day_len / 2.0

    solar_noon_h_utc = 12.0 - (lon * 4 + eot) / 60.0
    sn_hour = int(solar_noon_h_utc) % 24
    sn_min = int((solar_noon_h_utc % 1) * 60)
    solar_noon_str = f"{sn_hour:02d}:{sn_min:02d} UTC"

    # Clear-sky irradiance (Ineichen-Perez model)
    is_day = elev_deg > 0
    if is_day:
        # Air mass (Kasten & Young, 1989)
        zenith_r = math.radians(zenith_deg)
        am = 1.0 / (math.cos(zenith_r) + 0.50572 * (96.07995 - zenith_deg) ** -1.6364)
        am = max(am, 1.0)

        # Altitude correction
        p_ratio = math.exp(-altitude_m / 8434.5)
        am_corrected = am * p_ratio

        # Extraterrestrial irradiance with eccentricity correction
        day_of_year = dt.timetuple().tm_yday
        ecc = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
        I0 = 1361.0 * ecc  # W/m2

        # Ineichen clear-sky model (simplified)
        fh1 = math.exp(-altitude_m / 8000.0)
        fh2 = math.exp(-altitude_m / 1250.0)
        cg1 = 5.09e-5 * altitude_m + 0.868
        cg2 = 3.92e-5 * altitude_m + 0.0387

        dni = (
            cg1 * I0 * math.exp(-cg2 * am_corrected * (fh1 + fh2 * (linke_turbidity - 1)))
        )
        dni = max(dni, 0.0)

        # GHI and DHI
        ghi_clear = max(0.0, dni * math.cos(zenith_r) + 100.0 * (1 - fh1))
        dhi = max(0.0, ghi_clear - dni * math.cos(zenith_r))
        ghi = ghi_clear
    else:
        dni, ghi, dhi = 0.0, 0.0, 0.0

    # Convert GHI to illuminance (lux)
    # Luminous efficacy ~110 lm/W for clear sky daylight
    if ghi > 0:
        lux = ghi * 110.0
    elif is_day:
        lux = 500.0  # overcast minimum
    else:
        # Moonlight/twilight
        if elev_deg > -6:
            lux = max(1.0, 500 * (1 + elev_deg / 6.0))  # civil twilight
        elif elev_deg > -12:
            lux = 1.0  # nautical twilight
        else:
            lux = 0.1  # astronomical twilight / night

    return SolarPosition(
        elevation_deg=round(elev_deg, 2),
        azimuth_deg=round(azimuth, 2),
        zenith_deg=round(zenith_deg, 2),
        hour_angle_deg=round(hour_angle, 2),
        declination_deg=round(dec_deg, 2),
        sunrise_hour=round(sunrise_h, 2),
        sunset_hour=round(sunset_h, 2),
        day_length_hr=round(day_len, 2),
        ghi_w_m2=round(ghi, 1),
        dni_w_m2=round(dni, 1),
        dhi_w_m2=round(dhi, 1),
        illuminance_lux=round(lux, 0),
        solar_noon_utc=solar_noon_str,
        is_daytime=is_day,
    )
