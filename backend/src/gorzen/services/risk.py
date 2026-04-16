"""Ground-risk model (SORA-inspired) for VTOL mission planning.

Computes a per-leg ground-risk score based on:

* **Population density** under the flight path (people per km²), looked
  up from a pluggable :class:`PopulationRaster`.
* **Crash cone geometry** — a Monte-Carlo dispersion of impact points
  under loss-of-thrust, parameterised by altitude and airspeed. We
  approximate the cone as a disk whose radius grows as
  ``r = altitude * tan(glide_angle)`` plus a lateral Gaussian from
  attitude uncertainty.
* **ALARP / SORA thresholds** — the FAA SORA methodology buckets
  missions into GRC (Ground Risk Class) 1-7 based on expected people
  per hour of exposure. We map the expected fatalities per flight hour
  onto GRC, and the operator decides whether to accept the mission.

The integration target is minimal — a single :func:`assess_mission_risk`
function that the pre-flight checklist can call with a mission plan and
a population raster. The raster is represented by a simple callable so
callers can plug in GPW v4 / WorldPop / a custom GeoJSON without this
module depending on GDAL.

References:
    JARUS SORA v2.0 Annex A (Semantic Model of Risk).
    Melnyk et al., "A third-party casualty risk model for UAS",
    RESS Vol. 124, 2014.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Sequence

import numpy as np

from gorzen.schemas.mission import MissionPlan, Waypoint


EARTH_R = 6_371_000.0


class SoraGrc(int, Enum):
    """FAA SORA Ground Risk Class (1 = lowest, 7 = highest)."""

    GRC_1 = 1
    GRC_2 = 2
    GRC_3 = 3
    GRC_4 = 4
    GRC_5 = 5
    GRC_6 = 6
    GRC_7 = 7


# SORA GRC thresholds: approx people per km² below which the class holds
# for VTOL / fixed-wing with the canonical 3-8 m critical diameter. Upper
# bounds follow JARUS SORA Annex A (simplified).
SORA_GRC_THRESHOLDS_PPKM2 = [
    (0.1, SoraGrc.GRC_1),     # Controlled area / unmanned
    (2.0, SoraGrc.GRC_2),     # Sparse rural
    (50.0, SoraGrc.GRC_3),    # Rural
    (250.0, SoraGrc.GRC_4),   # Suburban
    (1_000.0, SoraGrc.GRC_5), # Urban
    (10_000.0, SoraGrc.GRC_6),# Dense urban
]


@dataclass
class PopulationRaster:
    """Lookup callable for population density (people per km²)."""

    lookup: Callable[[float, float], float]
    #: Nominal resolution of the underlying raster, in metres, for docs only.
    resolution_m: float = 1_000.0

    def at(self, lat: float, lon: float) -> float:
        return max(0.0, float(self.lookup(lat, lon)))


@dataclass
class CrashConeModel:
    """Monte-Carlo crash dispersion after a loss-of-thrust event.

    The simplified model treats the aircraft as a point mass with an
    average glide angle ``glide_angle_deg``. Uncertainty in the escape
    attitude is represented by a 2-D Gaussian whose standard deviation
    grows linearly with altitude. Bigger / faster aircraft don't glide
    as cleanly, so ``glide_angle_deg`` should come from flight testing.
    """

    glide_angle_deg: float = 15.0
    lateral_sigma_per_m_alt: float = 0.05
    #: Expected lethal area per impact (m²). Parry 2003 uses 30 m² for a
    #: typical small UAS; large VTOLs with composite airframes can exceed 100.
    lethal_area_m2: float = 30.0

    def impact_radius_m(self, altitude_agl_m: float, airspeed_ms: float) -> float:
        """Best-case glide radius (deterministic part of the dispersion)."""
        return altitude_agl_m * math.tan(math.radians(self.glide_angle_deg)) + airspeed_ms * 2.0

    def sample_impact_points(
        self,
        centre: tuple[float, float],
        altitude_agl_m: float,
        airspeed_ms: float,
        n_samples: int = 500,
        seed: int | None = 0,
    ) -> np.ndarray:
        """Return shape ``(n_samples, 2)`` impact points (lat, lon)."""
        rng = np.random.default_rng(seed)
        r_nom = self.impact_radius_m(altitude_agl_m, airspeed_ms)
        sigma = self.lateral_sigma_per_m_alt * altitude_agl_m + 2.0
        # Isotropic draw: bearing uniform, range ~ |N(r_nom, sigma)|.
        bearings = rng.uniform(0, 2 * math.pi, n_samples)
        ranges = np.abs(rng.normal(r_nom, sigma, n_samples))
        lat0, lon0 = centre
        d_lat = (ranges * np.cos(bearings)) / EARTH_R * (180.0 / math.pi)
        d_lon = (ranges * np.sin(bearings)) / (
            EARTH_R * math.cos(math.radians(lat0))
        ) * (180.0 / math.pi)
        return np.column_stack([lat0 + d_lat, lon0 + d_lon])


@dataclass
class MissionRiskAssessment:
    """Outcome of :func:`assess_mission_risk`."""

    expected_fatalities_per_hour: float
    grc: SoraGrc
    max_population_density: float
    mean_population_density: float
    details_by_waypoint: list[dict[str, float]] = field(default_factory=list)

    def acceptable(self, max_grc: SoraGrc = SoraGrc.GRC_4) -> bool:
        return self.grc.value <= max_grc.value


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return EARTH_R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _grc_for_density(pop_per_km2: float) -> SoraGrc:
    for thresh, grc in SORA_GRC_THRESHOLDS_PPKM2:
        if pop_per_km2 <= thresh:
            return grc
    return SoraGrc.GRC_7


def assess_mission_risk(
    plan: MissionPlan,
    population: PopulationRaster,
    cone: CrashConeModel,
    cruise_airspeed_ms: float,
    failure_rate_per_hour: float = 1e-3,
    home_elevation_m_msl: float = 0.0,
    n_mc_samples_per_leg: int = 300,
) -> MissionRiskAssessment:
    """Expected fatalities per flight hour along the mission.

    We integrate the expected casualty rate along each leg:

        rate(leg) = failure_rate * leg_time / mission_time
                    * E[pop_density] * lethal_area_m2

    and sum across legs. The maximum density seen on any leg is also
    reported so urban overflight can be flagged even if the mission-wide
    average looks safe.
    """
    if not plan.waypoints:
        raise ValueError("Mission plan is empty; nothing to assess")
    legs: list[tuple[Waypoint, Waypoint]] = []
    for i in range(1, len(plan.waypoints)):
        legs.append((plan.waypoints[i - 1], plan.waypoints[i]))

    details: list[dict[str, float]] = []
    expected_per_hour = 0.0
    max_density = 0.0
    sum_density_weighted = 0.0
    total_time_s = max(plan.estimated_duration_s, 1e-3)

    for i, (a, b) in enumerate(legs):
        leg_m = _haversine_m(a.latitude_deg, a.longitude_deg, b.latitude_deg, b.longitude_deg)
        leg_time_s = (
            leg_m / max(cruise_airspeed_ms, 1e-3)
            if cruise_airspeed_ms > 0
            else total_time_s / max(len(legs), 1)
        )
        mid = (
            0.5 * (a.latitude_deg + b.latitude_deg),
            0.5 * (a.longitude_deg + b.longitude_deg),
        )
        altitude_agl_m = max(a.altitude_m, b.altitude_m)
        impacts = cone.sample_impact_points(
            centre=mid,
            altitude_agl_m=altitude_agl_m,
            airspeed_ms=cruise_airspeed_ms,
            n_samples=n_mc_samples_per_leg,
            seed=i,
        )
        densities = np.array([population.at(la, lo) for la, lo in impacts])
        mean_density = float(np.mean(densities))
        peak = float(np.max(densities))
        max_density = max(max_density, peak)
        # Expected fatalities in this leg:
        #   lethal_area_km2 = cone.lethal_area_m2 / 1e6
        #   expected_people = mean_density * lethal_area_km2
        #   rate_leg = failure_rate * (leg_time_s / 3600) * expected_people
        lethal_area_km2 = cone.lethal_area_m2 / 1_000_000.0
        rate_leg = (
            failure_rate_per_hour * (leg_time_s / 3600.0) * mean_density * lethal_area_km2
        )
        expected_per_hour += rate_leg * (3600.0 / max(leg_time_s, 1e-3))
        sum_density_weighted += mean_density * leg_time_s
        details.append(
            {
                "leg_index": float(i),
                "leg_distance_m": leg_m,
                "altitude_agl_m": float(altitude_agl_m),
                "mean_density_ppkm2": mean_density,
                "peak_density_ppkm2": peak,
                "expected_fatalities_per_hour": rate_leg * 3600.0 / max(leg_time_s, 1e-3),
            }
        )
    total_leg_time = sum(d["leg_distance_m"] / max(cruise_airspeed_ms, 1e-3) for d in details)
    mean_density = sum_density_weighted / max(total_leg_time, 1e-3)
    # Use peak density (not average) for GRC so urban overflight is never
    # diluted by the long rural stretch that dominates the mean.
    grc = _grc_for_density(max_density)
    # Expected fatalities per hour — average of per-leg rates weighted by
    # leg duration.
    expected_fatalities = sum(
        d["expected_fatalities_per_hour"] * (d["leg_distance_m"] / max(cruise_airspeed_ms, 1e-3))
        for d in details
    ) / max(total_leg_time, 1e-3)

    return MissionRiskAssessment(
        expected_fatalities_per_hour=float(expected_fatalities),
        grc=grc,
        max_population_density=float(max_density),
        mean_population_density=float(mean_density),
        details_by_waypoint=details,
    )


def uniform_density_raster(people_per_km2: float) -> PopulationRaster:
    """Convenience constructor for a flat population field (useful for tests / rural)."""
    return PopulationRaster(lookup=lambda _la, _lo: people_per_km2, resolution_m=1e9)


__all__ = [
    "CrashConeModel",
    "MissionRiskAssessment",
    "PopulationRaster",
    "SORA_GRC_THRESHOLDS_PPKM2",
    "SoraGrc",
    "assess_mission_risk",
    "uniform_density_raster",
]
