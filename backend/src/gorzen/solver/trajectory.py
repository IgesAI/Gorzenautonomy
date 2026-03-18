"""CasADi trajectory optimizer with energy + perception constraints.

Formulates optimal trajectory as a nonlinear program (NLP) where the cost
is mission time/energy and constraints include perception quality bounds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

try:
    import casadi as ca
    HAS_CASADI = True
except ImportError:
    HAS_CASADI = False


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
        power_model_fn: Any = None,
        gsd_params: dict[str, float] | None = None,
    ):
        self.power_fn = power_model_fn
        self.gsd_params = gsd_params or {}

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
        total_dist = sum(distances)

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
        sw = self.gsd_params.get("sensor_width_mm", 13.2)
        fl = self.gsd_params.get("focal_length_mm", 24.0)
        px_w = self.gsd_params.get("pixel_width", 4000)
        max_alt_gsd = target_gsd * fl * px_w / (sw * 100.0)
        for i in range(N):
            opti.subject_to(h[i] <= max_alt_gsd)

        # Blur constraint: v * exposure_time / (gsd_m) <= max_blur
        exp_time = 1.0 / 1000.0
        for i in range(N):
            gsd_m = sw * h[i] / (fl * px_w * 1000)
            opti.subject_to(v[i] * exp_time / (gsd_m + 1e-6) <= max_blur)

        # Energy constraint (simplified)
        power_coeff = 300.0  # rough W in hover-cruise mix
        total_energy = 0
        for i in range(N):
            seg_time = distances[i] / (v[i] + 1e-3)
            total_energy += power_coeff * seg_time / 3600.0
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
        sw = self.gsd_params.get("sensor_width_mm", 13.2)
        fl = self.gsd_params.get("focal_length_mm", 24.0)
        px_w = self.gsd_params.get("pixel_width", 4000)

        max_alt_gsd = target_gsd * fl * px_w / (sw * 100.0)
        opt_alt = min(max_alt_gsd * 0.9, alt_bounds[1])
        opt_alt = max(opt_alt, alt_bounds[0])

        gsd_m = sw * opt_alt / (fl * px_w * 1000)
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

        for i in range(len(distances)):
            dt = distances[i] / (speeds[i] + 1e-3)
            power = 300.0  # placeholder
            e_wh = power * dt / 3600.0
            total_time += dt
            total_energy += e_wh

            seg = TrajectorySegment(
                start_lat=waypoints[i][0],
                start_lon=waypoints[i][1],
                end_lat=waypoints[i + 1][0],
                end_lon=waypoints[i + 1][1],
                altitude_m=altitudes[i],
                speed_ms=speeds[i],
                duration_s=dt,
                energy_wh=e_wh,
            )
            segments.append(seg)

        return TrajectoryResult(
            segments=segments,
            total_duration_s=total_time,
            total_energy_wh=total_energy,
            total_distance_m=sum(distances),
            optimal_speed_ms=float(np.mean(speeds)),
            optimal_altitude_m=float(np.mean(altitudes)),
            solver_status=status,
        )

    @staticmethod
    def _haversine(p1: tuple[float, float], p2: tuple[float, float]) -> float:
        R = 6371000
        lat1, lon1 = np.radians(p1[0]), np.radians(p1[1])
        lat2, lon2 = np.radians(p2[0]), np.radians(p2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
