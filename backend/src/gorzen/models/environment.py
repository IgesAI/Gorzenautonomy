"""Environment model: Dryden/Von Karman turbulence, lighting, temperature."""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel


class DrydenTurbulence:
    """Dryden continuous turbulence model (MIL-F-8785C).

    Generates wind turbulence by filtering white noise through transfer functions
    parameterized by wind speed at 6m and altitude.
    """

    def __init__(self, wind_speed_6m: float = 5.0, altitude_m: float = 50.0):
        self.update_params(wind_speed_6m, altitude_m)

    def update_params(self, wind_speed_6m: float, altitude_m: float) -> None:
        h = max(altitude_m, 3.0)
        self.Lu = h / (0.177 + 0.000823 * h) ** 1.2
        self.Lv = self.Lu
        self.Lw = h
        self.sigma_w = 0.1 * wind_speed_6m
        self.sigma_u = self.sigma_w / (0.177 + 0.000823 * h) ** 0.4
        self.sigma_v = self.sigma_u

    def sample(self, V: float, dt: float, n_steps: int, rng: np.random.Generator | None = None) -> np.ndarray:
        """Generate turbulence velocity samples [n_steps x 3] (u, v, w components).
        Uses fixed seed when rng is None for deterministic behavior."""
        if rng is None:
            rng = np.random.default_rng(42)

        white = rng.standard_normal((n_steps, 3))
        turb = np.zeros((n_steps, 3))

        V = max(V, 0.5)
        au = V / (self.Lu + 1e-6)
        av = V / (self.Lv + 1e-6)
        aw = V / (self.Lw + 1e-6)

        for i in range(1, n_steps):
            turb[i, 0] = (1 - au * dt) * turb[i - 1, 0] + self.sigma_u * np.sqrt(2 * au * dt) * white[i, 0]
            turb[i, 1] = (1 - av * dt) * turb[i - 1, 1] + self.sigma_v * np.sqrt(2 * av * dt) * white[i, 1]
            turb[i, 2] = (1 - aw * dt) * turb[i - 1, 2] + self.sigma_w * np.sqrt(2 * aw * dt) * white[i, 2]

        return turb


class VonKarmanTurbulence:
    """Von Karman turbulence model.

    Often considered to better match real continuous turbulence measurements.
    Uses spatial frequency domain shaping.
    """

    def __init__(self, wind_speed_6m: float = 5.0, altitude_m: float = 50.0):
        self.update_params(wind_speed_6m, altitude_m)

    def update_params(self, wind_speed_6m: float, altitude_m: float) -> None:
        h = max(altitude_m, 3.0)
        self.Lu = h / (0.177 + 0.000823 * h) ** 1.2
        self.Lw = h
        self.sigma_w = 0.1 * wind_speed_6m
        self.sigma_u = self.sigma_w / (0.177 + 0.000823 * h) ** 0.4

    def sample(self, V: float, dt: float, n_steps: int, rng: np.random.Generator | None = None) -> np.ndarray:
        """Generate turbulence samples. Uses fixed seed when rng is None for deterministic behavior."""
        if rng is None:
            rng = np.random.default_rng(42)
        # Approximate Von Karman via filtered noise (similar shape, different spectral roll-off)
        white = rng.standard_normal((n_steps, 3))
        turb = np.zeros((n_steps, 3))
        V = max(V, 0.5)
        au = 1.339 * V / (self.Lu + 1e-6)
        aw = 1.339 * V / (self.Lw + 1e-6)
        for i in range(1, n_steps):
            turb[i, 0] = (1 - au * dt) * turb[i - 1, 0] + self.sigma_u * np.sqrt(2 * au * dt) * white[i, 0]
            turb[i, 1] = (1 - au * dt) * turb[i - 1, 1] + self.sigma_u * np.sqrt(2 * au * dt) * white[i, 1]
            turb[i, 2] = (1 - aw * dt) * turb[i - 1, 2] + self.sigma_w * np.sqrt(2 * aw * dt) * white[i, 2]
        return turb


GUST_INTENSITY_MAP = {
    "light": 0.5,
    "moderate": 1.0,
    "severe": 2.0,
}


class EnvironmentModel(SubsystemModel):
    """Combined environment model: wind, turbulence, lighting, temperature."""

    def parameter_names(self) -> list[str]:
        return [
            "wind_model", "wind_speed_ms", "gust_intensity",
            "wind_direction_deg", "temperature_c", "pressure_hpa",
            "ambient_light_lux",
        ]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return [
            "headwind_ms", "crosswind_ms", "turbulence_intensity",
            "air_density_kgm3", "temperature_at_alt_c",
            "ambient_light_lux_out",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        wind_speed = params.get("wind_speed_ms", 5.0)
        wind_dir = params.get("wind_direction_deg", 0.0)
        gust = str(params.get("gust_intensity", "moderate"))
        temp = params.get("temperature_c", 20.0)
        pressure = params.get("pressure_hpa", 1013.25)
        light = params.get("ambient_light_lux", 10000.0)

        alt = conditions.get("altitude_m", 50.0)
        heading = conditions.get("heading_deg", 0.0)

        # Wind components relative to flight direction
        rel_angle = np.radians(wind_dir - heading)
        headwind = wind_speed * np.cos(rel_angle)
        crosswind = wind_speed * np.sin(rel_angle)

        gust_factor = GUST_INTENSITY_MAP.get(gust, 1.0)
        turb_intensity = wind_speed * 0.1 * gust_factor

        # ISA with temperature offset (ideal gas: rho = rho0 * (P/P0) * (T0/T))
        isa_temp_K = 288.15 - 0.0065 * alt
        T_actual_K = isa_temp_K + (temp - 15.0)  # non-standard day
        rho = 1.225 * (pressure / 1013.25) * (288.15 / (T_actual_K + 1e-6))
        temp_at_alt = temp - 0.0065 * alt

        return ModelOutput(
            values={
                "headwind_ms": headwind,
                "crosswind_ms": crosswind,
                "turbulence_intensity": turb_intensity,
                "air_density_kgm3": rho,
                "temperature_at_alt_c": temp_at_alt,
                "ambient_light_lux_out": light,
            },
            units={
                "headwind_ms": "m/s", "crosswind_ms": "m/s",
                "turbulence_intensity": "m/s", "air_density_kgm3": "kg/m3",
                "temperature_at_alt_c": "degC", "ambient_light_lux_out": "lux",
            },
        )
