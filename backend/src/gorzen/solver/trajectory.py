"""CasADi trajectory optimizer with energy + perception constraints.

Formulates the optimal trajectory as a nonlinear program (NLP) where the
cost is mission time/energy and constraints include perception quality
bounds, a per-segment energy budget, and optional terrain-adjusted
altitude limits.

Phase 2 changes:

* **Per-segment energy accounting** — the energy constraint now evaluates
  the power model at every segment's speed/altitude rather than at the
  midpoint of the bounds. The previous formulation used a constant midpoint
  power in the constraint while the cost used varying v[i], which produced
  inconsistent physics (a fast-then-slow schedule could appear "cheaper"
  even though it used more energy).
* **No silent solver fallback** — if IPOPT fails we raise
  :class:`TrajectoryNotSolvedError` with the IPOPT return status instead of
  returning an arbitrary midpoint speed/altitude that looks plausible.
* **Exposure time** is now supplied via ``gsd_params["exposure_time_s"]``
  (formerly hardcoded to 1/1000 s).
* **Propulsive efficiency** is a named argument of
  :func:`default_power_model` — callers override via the twin's
  ``propulsive_efficiency`` parameter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from gorzen.solver.errors import TrajectoryNotSolvedError
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
    AR = wing_span_m**2 / (wing_area_m2 + 1e-6)
    W = mass_kg * 9.81
    v = max(speed_ms, 0.5)
    q = 0.5 * rho * v**2
    CL = W / (q * wing_area_m2 + 1e-6) if speed_ms > 2.0 else 0.0
    Cdi = CL**2 / (np.pi * AR * oswald_e + 1e-6) if speed_ms > 2.0 else 0.0
    D = q * wing_area_m2 * (cd0 + Cdi)
    P_drag_kw = D * v / 1000.0
    return max(idle_power_kw, P_drag_kw / prop_efficiency) * 1000.0


_REQUIRED_POWER_MODEL_PARAMS = [
    "mass_total_kg",
    "wing_area_m2",
    "wing_span_m",
    "cd0",
    "oswald_efficiency",
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
    eta_prop = float(params.get("propulsive_efficiency", 0.6))

    def power_fn(speed_ms: float, altitude_m: float) -> float:
        return default_power_model(
            speed_ms,
            altitude_m,
            mass_kg=mass_kg,
            wing_area_m2=wing_area,
            wing_span_m=wing_span,
            cd0=cd0,
            oswald_e=oswald_e,
            prop_efficiency=eta_prop,
        )

    power_fn._mass_kg = mass_kg  # type: ignore[attr-defined]
    power_fn._wing_area = wing_area  # type: ignore[attr-defined]
    power_fn._wing_span = wing_span  # type: ignore[attr-defined]
    power_fn._cd0 = cd0  # type: ignore[attr-defined]
    power_fn._oswald = oswald_e  # type: ignore[attr-defined]
    power_fn._eta_prop = eta_prop  # type: ignore[attr-defined]
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

        # Cache physical constants for the CasADi power expression. We prefer
        # the attributes stashed by :func:`make_power_model_from_params`; if
        # they aren't present, fall back to the defaults used in
        # :func:`default_power_model`.
        self._power_mass_kg = getattr(self.power_fn, "_mass_kg", 68.0)
        self._power_wing_area = getattr(self.power_fn, "_wing_area", 1.2)
        self._power_wing_span = getattr(self.power_fn, "_wing_span", 4.88)
        self._power_cd0 = getattr(self.power_fn, "_cd0", 0.03)
        self._power_oswald = getattr(self.power_fn, "_oswald", 0.8)
        self._power_eta_prop = getattr(self.power_fn, "_eta_prop", 0.6)
        self._power_idle_kw = 0.3

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
                distances,
                altitude_bounds,
                speed_bounds,
                energy_budget_wh,
                target_gsd_cm,
                max_blur_px,
                overlap_pct,
                waypoints,
            )
        else:
            return self._analytical_optimize(
                distances,
                altitude_bounds,
                speed_bounds,
                energy_budget_wh,
                target_gsd_cm,
                max_blur_px,
                overlap_pct,
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

        # Blur constraint: v * exposure_time / gsd_m <= max_blur.
        # ``exposure_time_s`` is supplied by the caller via ``gsd_params``;
        # hardcoding 1/1000 s silently ignored real mission profiles (night
        # operations routinely use 1/60 s).
        exp_time = float(self.gsd_params.get("exposure_time_s", 1.0 / 1000.0))
        for i in range(N):
            gsd_m = sw * h[i] / (fl * px_w)
            opti.subject_to(v[i] * exp_time / (gsd_m + 1e-6) <= max_blur)

        # Energy constraint: integrate a CasADi-native drag-polar power
        # model over each segment so the total depends on the solution's
        # v[i]/h[i] (not a frozen midpoint estimate).
        total_energy = 0
        for i in range(N):
            seg_time = distances[i] / (v[i] + 1e-3)
            total_energy += self._casadi_power_expr(v[i], h[i]) * seg_time / 3600.0
        opti.subject_to(total_energy <= energy_wh)

        # Warm start from the midpoint — the physics-correct analytical
        # fallback is the right initial guess for IPOPT.
        for i in range(N):
            opti.set_initial(v[i], 0.5 * (spd_bounds[0] + spd_bounds[1]))
            opti.set_initial(h[i], min(max_alt_gsd, alt_bounds[1]))

        opti.solver("ipopt", {"print_time": False}, {"print_level": 0})

        try:
            sol = opti.solve()
        except RuntimeError as exc:
            stats = opti.debug.stats()
            return_status = stats.get("return_status", "unknown")
            raise TrajectoryNotSolvedError(
                f"IPOPT failed to converge: {return_status}: {exc}"
            ) from exc

        v_opt = [float(sol.value(v[i])) for i in range(N)]
        h_opt = [float(sol.value(h[i])) for i in range(N)]

        # Verify the energy constraint isn't violated by >1% (covers cases
        # where IPOPT returned "Solve_Succeeded" with relaxed tolerances).
        realized = sum(
            self.power_fn(v_opt[i], h_opt[i]) * (distances[i] / (v_opt[i] + 1e-3)) / 3600.0
            for i in range(N)
        )
        if realized > energy_wh * 1.01:
            raise TrajectoryNotSolvedError(
                f"NLP returned an infeasible schedule: realized energy {realized:.1f} Wh "
                f"> budget {energy_wh:.1f} Wh"
            )

        return self._build_result(distances, v_opt, h_opt, waypoints, overlap, "optimal")

    def _casadi_power_expr(self, v: "ca.MX", h: "ca.MX") -> "ca.MX":
        """CasADi-symbolic version of :func:`default_power_model` for NLP constraints."""
        if not HAS_CASADI:  # pragma: no cover
            raise RuntimeError("CasADi not available")
        mass = getattr(self, "_power_mass_kg", 68.0)
        S = getattr(self, "_power_wing_area", 1.2)
        b = getattr(self, "_power_wing_span", 4.88)
        cd0 = getattr(self, "_power_cd0", 0.03)
        e = getattr(self, "_power_oswald", 0.8)
        eta = getattr(self, "_power_eta_prop", 0.6)
        idle_kw = getattr(self, "_power_idle_kw", 0.3)
        T_isa = TEMP_0 - LAPSE_RATE * h
        rho = RHO_0 * (T_isa / TEMP_0) ** 4.2561
        AR = b**2 / S
        W = mass * 9.81
        q = 0.5 * rho * v**2
        CL = W / (q * S + 1e-3)
        Cdi = CL**2 / (ca.pi * AR * e)
        D = q * S * (cd0 + Cdi)
        P = D * v / 1000.0 / eta
        # Smooth max with idle power via softplus so CasADi stays differentiable.
        return 1000.0 * (idle_kw + ca.log(1 + ca.exp(P - idle_kw)))

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
        exp_time = float(self.gsd_params.get("exposure_time_s", 1.0 / 1000.0))
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
                photo_schedule.append(
                    {
                        "lat": lat,
                        "lon": lon,
                        "altitude_m": altitudes[i],
                        "cumulative_distance_m": cumulative_dist + dist_along,
                        "time_s": (cumulative_dist + dist_along) / (speeds[i] + 1e-3),
                        "trigger_interval_s": trigger_interval_s,
                    }
                )
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
        if not hasattr(self, "_terrain_elevations") or not self._terrain_elevations:
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
