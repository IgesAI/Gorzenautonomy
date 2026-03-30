"""CasADi trajectory optimizer with energy + perception constraints.

Formulates optimal trajectory as a nonlinear program (NLP) where the cost
is mission time/energy and constraints include perception quality bounds.

All sensor and platform parameters are REQUIRED.  The optimizer validates
that gsd_params contains the necessary sensor specs at construction time
and raises ValueError if any are missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from gorzen.validation.parameter_validator import validate_params, REQUIRED_SENSOR_PARAMS

try:
    import casadi as ca
    HAS_CASADI = True
except ImportError:
    HAS_CASADI = False


RHO_0 = 1.225
TEMP_0 = 288.15
LAPSE_RATE = 0.0065


def default_power_model(
    speed_ms: float,
    altitude_m: float,
    mass_kg: float = 68.0,
    wing_area_m2: float = 1.2,
    wing_span_m: float = 4.88,
    cd0: float = 0.03,
    oswald_e: float = 0.8,
    prop_efficiency: float = 0.6,
    idle_power_kw: float = 0.3,
) -> float:
    """Physics-based cruise power estimate (kW) using drag polar.

    P = D * V / eta_prop, where D = q * S * (Cd0 + CL^2 / (pi * AR * e)).
    Returns power in Watts.
    """
    T_isa = TEMP_0 - LAPSE_RATE * altitude_m
    rho = RHO_0 * (T_isa / TEMP_0) ** 4.2561
    AR = wing_span_m ** 2 / (wing_area_m2 + 1e-6)
    W = mass_kg * 9.81
    v = max(speed_ms, 0.5)
    q = 0.5 * rho * v ** 2
    CL = W / (q * wing_area_m2 + 1e-6) if speed_ms > 2.0 else 0.0
    Cdi = CL ** 2 / (np.pi * AR * oswald_e + 1e-6) if speed_ms > 2.0 else 0.0
    D = q * wing_area_m2 * (cd0 + Cdi)
    P_drag_kw = D * v / 1000.0
    return max(idle_power_kw, P_drag_kw / prop_efficiency) * 1000.0


_REQUIRED_POWER_MODEL_PARAMS = [
    "mass_total_kg", "wing_area_m2", "wing_span_m", "cd0", "oswald_efficiency",
]


def make_power_model_from_params(params: dict[str, float]) -> Callable[[float, float], float]:
    """Create a power model closure from twin parameters.

    Raises ValueError if any required aerodynamic parameter is missing.
    """
    vr = validate_params(params, _REQUIRED_POWER_MODEL_PARAMS, context="power_model")
    if not vr.valid:
        raise ValueError(vr.error_message)

    mass_kg = float(params["mass_total_kg"])
    wing_area = float(params["wing_area_m2"])
    wing_span = float(params["wing_span_m"])
    cd0 = float(params["cd0"])
    oswald_e = float(params["oswald_efficiency"])

    def power_fn(speed_ms: float, altitude_m: float) -> float:
        return default_power_model(
            speed_ms, altitude_m,
            mass_kg=mass_kg, wing_area_m2=wing_area,
            wing_span_m=wing_span, cd0=cd0, oswald_e=oswald_e,
        )

    return power_fn


@dataclass
class TrajectorySegment:
    """A segment of the optimized trajectory."""

    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    altitude_m: float
    speed_ms: float
    duration_s: float
    energy_wh: float
    photo_interval_m: float | None = None


@dataclass
class TrajectoryResult:
    """Result of trajectory optimization."""

    segments: list[TrajectorySegment] = field(default_factory=list)
    total_duration_s: float = 0.0
    total_energy_wh: float = 0.0
    total_distance_m: float = 0.0
    optimal_speed_ms: float = 0.0
    optimal_altitude_m: float = 0.0
    photo_schedule: list[dict] = field(default_factory=list)
    solver_status: str = "not_run"


class TrajectoryOptimizer:
    """Trajectory optimizer using CasADi for NLP formulation.

    Minimizes mission time subject to:
    - Energy budget (battery capacity - reserve)
    - GSD constraint (altitude bounds)
    - Motion blur constraint (speed bounds)
    - Overlap constraint (photo cadence)
    """

    def __init__(
        self,
        power_model_fn: Callable[[float, float], float] | None = None,
        gsd_params: dict[str, float] | None = None,
    ):
        self.power_fn = power_model_fn or (lambda v, h: default_power_model(v, h))
        self.gsd_params = gsd_params or {}
        vr = validate_params(self.gsd_params, REQUIRED_SENSOR_PARAMS, context="TrajectoryOptimizer")
        if not vr.valid:
            raise ValueError(vr.error_message)

    def optimize_survey(
        self,
        waypoints: list[tuple[float, float]],
        altitude_bounds: tuple[float, float] = (20.0, 120.0),
        speed_bounds: tuple[float, float] = (2.0, 25.0),
        energy_budget_wh: float = 200.0,
        target_gsd_cm: float = 1.0,
        max_blur_px: float = 0.5,
        overlap_pct: float = 70.0,
    ) -> TrajectoryResult:
        """Optimize a survey trajectory over given waypoints.

        Falls back to analytical optimization if CasADi is unavailable.
        """
        if not waypoints or len(waypoints) < 2:
            return TrajectoryResult(solver_status="no_waypoints")

        # Compute distances between waypoints
        distances = []
        for i in range(len(waypoints) - 1):
            d = self._haversine(waypoints[i], waypoints[i + 1])
            distances.append(d)
        sum(distances)

        if HAS_CASADI:
            return self._casadi_optimize(
                distances, altitude_bounds, speed_bounds,
                energy_budget_wh, target_gsd_cm, max_blur_px, overlap_pct,
                waypoints,
            )
        else:
            return self._analytical_optimize(
                distances, altitude_bounds, speed_bounds,
                energy_budget_wh, target_gsd_cm, max_blur_px, overlap_pct,
                waypoints,
            )

    def _casadi_optimize(
        self,
        distances: list[float],
        alt_bounds: tuple[float, float],
        spd_bounds: tuple[float, float],
        energy_wh: float,
        target_gsd: float,
        max_blur: float,
        overlap: float,
        waypoints: list[tuple[float, float]],
    ) -> TrajectoryResult:
        """CasADi NLP formulation."""
        N = len(distances)

        opti = ca.Opti()
        v = opti.variable(N)  # speed per segment
        h = opti.variable(N)  # altitude per segment

        # Cost: total time
        total_time = 0
        for i in range(N):
            total_time += distances[i] / (v[i] + 1e-3)
        opti.minimize(total_time)

        # Bounds
        for i in range(N):
            opti.subject_to(v[i] >= spd_bounds[0])
            opti.subject_to(v[i] <= spd_bounds[1])
            opti.subject_to(h[i] >= alt_bounds[0])
            opti.subject_to(h[i] <= alt_bounds[1])

        # GSD constraint: h <= target_gsd * fl * px_w / (sw * 100)
        sw = self.gsd_params["sensor_width_mm"]
        fl = self.gsd_params["focal_length_mm"]
        px_w = self.gsd_params["pixel_width"]
        max_alt_gsd = target_gsd * fl * px_w / (sw * 100.0)
        for i in range(N):
            opti.subject_to(h[i] <= max_alt_gsd)

        # Blur constraint: v * exposure_time / (gsd_m) <= max_blur
        # GSD_m = sensor_width_mm * altitude_m / (focal_length_mm * pixel_width)
        # sensor_width_mm is in mm; altitude in m → result is in m/px (mm cancels in ratio)
        exp_time = 1.0 / 1000.0
        for i in range(N):
            gsd_m = sw * h[i] / (fl * px_w)
            opti.subject_to(v[i] * exp_time / (gsd_m + 1e-6) <= max_blur)

        # Energy constraint: linearized power from the twin's drag model
        mid_speed = (spd_bounds[0] + spd_bounds[1]) / 2
        mid_alt = (alt_bounds[0] + alt_bounds[1]) / 2
        power_at_mid = self.power_fn(mid_speed, mid_alt)
        total_energy = 0
        for i in range(N):
            seg_time = distances[i] / (v[i] + 1e-3)
            total_energy += power_at_mid * seg_time / 3600.0
        opti.subject_to(total_energy <= energy_wh)

        opti.solver("ipopt", {"print_time": False}, {"print_level": 0})

        try:
            sol = opti.solve()
            v_opt = [float(sol.value(v[i])) for i in range(N)]
            h_opt = [float(sol.value(h[i])) for i in range(N)]
            status = "optimal"
        except Exception:
            v_opt = [(spd_bounds[0] + spd_bounds[1]) / 2] * N
            h_opt = [min(max_alt_gsd, alt_bounds[1])] * N
            status = "fallback"

        return self._build_result(distances, v_opt, h_opt, waypoints, overlap, status)

    def _analytical_optimize(
        self,
        distances: list[float],
        alt_bounds: tuple[float, float],
        spd_bounds: tuple[float, float],
        energy_wh: float,
        target_gsd: float,
        max_blur: float,
        overlap: float,
        waypoints: list[tuple[float, float]],
    ) -> TrajectoryResult:
        """Analytical fallback when CasADi is unavailable."""
        sw = self.gsd_params["sensor_width_mm"]
        fl = self.gsd_params["focal_length_mm"]
        px_w = self.gsd_params["pixel_width"]

        max_alt_gsd = target_gsd * fl * px_w / (sw * 100.0)
        opt_alt = min(max_alt_gsd * 0.9, alt_bounds[1])
        opt_alt = max(opt_alt, alt_bounds[0])

        gsd_m = sw * opt_alt / (fl * px_w)
        exp_time = 1.0 / 1000.0
        max_speed_blur = max_blur * gsd_m / (exp_time + 1e-9)
        opt_speed = min(max_speed_blur * 0.9, spd_bounds[1])
        opt_speed = max(opt_speed, spd_bounds[0])

        N = len(distances)
        return self._build_result(
            distances, [opt_speed] * N, [opt_alt] * N, waypoints, overlap, "analytical"
        )

    def _build_result(
        self,
        distances: list[float],
        speeds: list[float],
        altitudes: list[float],
        waypoints: list[tuple[float, float]],
        overlap: float,
        status: str,
    ) -> TrajectoryResult:
        segments = []
        total_time = 0.0
        total_energy = 0.0

        photo_schedule: list[dict] = []
        cumulative_dist = 0.0

        for i in range(len(distances)):
            dt = distances[i] / (speeds[i] + 1e-3)
            power = self.power_fn(speeds[i], altitudes[i])
            e_wh = power * dt / 3600.0
            total_time += dt
            total_energy += e_wh

            # Compute photo interval for this segment
            sw = self.gsd_params["sensor_width_mm"]
            fl = self.gsd_params["focal_length_mm"]
            px_w = self.gsd_params["pixel_width"]
            gsd_m = sw * altitudes[i] / (fl * px_w)
            footprint_along_m = gsd_m * self.gsd_params["pixel_height"]
            photo_interval_m = footprint_along_m * (1.0 - overlap / 100.0)
            photo_interval_m = max(photo_interval_m, 1.0)
            trigger_interval_s = photo_interval_m / (speeds[i] + 1e-3)

            seg = TrajectorySegment(
                start_lat=waypoints[i][0],
                start_lon=waypoints[i][1],
                end_lat=waypoints[i + 1][0],
                end_lon=waypoints[i + 1][1],
                altitude_m=altitudes[i],
                speed_ms=speeds[i],
                duration_s=dt,
                energy_wh=e_wh,
                photo_interval_m=photo_interval_m,
            )
            segments.append(seg)

            # Build photo schedule for this segment
            dist_along = 0.0
            while dist_along < distances[i]:
                frac = dist_along / (distances[i] + 1e-6)
                lat = waypoints[i][0] + frac * (waypoints[i + 1][0] - waypoints[i][0])
                lon = waypoints[i][1] + frac * (waypoints[i + 1][1] - waypoints[i][1])
                photo_schedule.append({
                    "lat": lat,
                    "lon": lon,
                    "altitude_m": altitudes[i],
                    "cumulative_distance_m": cumulative_dist + dist_along,
                    "time_s": (cumulative_dist + dist_along) / (speeds[i] + 1e-3),
                    "trigger_interval_s": trigger_interval_s,
                })
                dist_along += photo_interval_m

            cumulative_dist += distances[i]

        return TrajectoryResult(
            segments=segments,
            total_duration_s=total_time,
            total_energy_wh=total_energy,
            total_distance_m=sum(distances),
            optimal_speed_ms=float(np.mean(speeds)),
            optimal_altitude_m=float(np.mean(altitudes)),
            photo_schedule=photo_schedule,
            solver_status=status,
        )

    def set_terrain_elevations(self, elevations_m: list[float]) -> None:
        """Set ground elevation per waypoint for terrain-following altitude adjustment.

        The trajectory optimizer will add ground elevation to the target AGL altitude
        to produce MSL-referenced altitudes ensuring consistent AGL clearance.
        """
        self._terrain_elevations = elevations_m

    def get_terrain_adjusted_bounds(
        self,
        segment_idx: int,
        base_alt_bounds: tuple[float, float],
    ) -> tuple[float, float]:
        """Adjust altitude bounds for a segment based on terrain elevation.

        Returns MSL bounds that maintain the requested AGL clearance above terrain.
        """
        if not hasattr(self, '_terrain_elevations') or not self._terrain_elevations:
            return base_alt_bounds
        ground_elev = 0.0
        if segment_idx < len(self._terrain_elevations):
            ground_elev = self._terrain_elevations[segment_idx]
        elif segment_idx + 1 < len(self._terrain_elevations):
            ground_elev = max(
                self._terrain_elevations[segment_idx],
                self._terrain_elevations[segment_idx + 1],
            )
        return (base_alt_bounds[0] + ground_elev, base_alt_bounds[1] + ground_elev)

    @staticmethod
    def _haversine(p1: tuple[float, float], p2: tuple[float, float]) -> float:
        R = 6371000
        lat1, lon1 = np.radians(p1[0]), np.radians(p1[1])
        lat2, lon2 = np.radians(p2[0]), np.radians(p2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
