"""Airframe dynamics model: mode-aware lift+cruise VTOL with transitions.

Tier A (real-time): reduced-order rigid-body dynamics with calibrated force/torque models.
Supports hover, transition, and wingborne cruise flight modes.
"""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel

# ISA sea-level defaults
RHO_0 = 1.225  # kg/m^3
TEMP_0 = 288.15  # K
LAPSE_RATE = 0.0065  # K/m
G = 9.81  # m/s^2


def isa_density(altitude_m: float) -> float:
    """International Standard Atmosphere density."""
    T = TEMP_0 - LAPSE_RATE * altitude_m
    return RHO_0 * (T / TEMP_0) ** 4.2561


class AirframeModel(SubsystemModel):
    """Mode-aware airframe model for lift+cruise VTOL.

    Flight modes:
    - hover (v < v_transition_start): pure rotor lift
    - transition (v_transition_start <= v < v_transition_end): mixed lift
    - cruise (v >= v_transition_end): wing-borne with auxiliary rotor if needed
    """

    TRANSITION_START_FRAC = 0.3
    TRANSITION_END_FRAC = 0.6

    def parameter_names(self) -> list[str]:
        return [
            "mass_total_kg", "wing_area_m2", "wing_span_m",
            "cd0", "cl_alpha", "oswald_efficiency",
            "max_speed_ms", "max_load_factor",
        ]

    def state_names(self) -> list[str]:
        return ["flight_mode"]

    def output_names(self) -> list[str]:
        return [
            "drag_N", "lift_required_N", "wing_lift_N",
            "rotor_lift_required_N", "power_parasitic_W",
            "flight_mode_id", "load_factor", "aero_feasible",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        mass = params.get("mass_total_kg", 12.0)
        S = params.get("wing_area_m2", 0.5)
        b = params.get("wing_span_m", 2.0)
        cd0 = params.get("cd0", 0.03)
        cl_alpha = params.get("cl_alpha", 5.0)
        e = params.get("oswald_efficiency", 0.8)
        vne = params.get("max_speed_ms", 35.0)
        max_lf = params.get("max_load_factor", 3.0)

        v = conditions.get("airspeed_ms", 0.0)
        alt = conditions.get("altitude_m", 50.0)
        alpha_rad = conditions.get("alpha_rad", 0.05)

        # Use Environment model's air_density when available (pressure/temp-corrected)
        rho = conditions.get("air_density_kgm3")
        if rho is None or rho <= 0:
            rho = isa_density(alt)
        W = mass * G
        AR = b ** 2 / S if S > 0 else 10.0

        v_trans_start = vne * self.TRANSITION_START_FRAC
        v_trans_end = vne * self.TRANSITION_END_FRAC

        if v < v_trans_start:
            mode_id = 0.0  # hover
            wing_fraction = 0.0
        elif v < v_trans_end:
            mode_id = 1.0  # transition
            wing_fraction = (v - v_trans_start) / (v_trans_end - v_trans_start)
        else:
            mode_id = 2.0  # cruise
            wing_fraction = 1.0

        q = 0.5 * rho * v ** 2 if v > 0.1 else 0.0

        cl = cl_alpha * alpha_rad if v > 0.1 else 0.0
        wing_lift = q * S * cl
        wing_lift = min(wing_lift, W)
        wing_lift *= wing_fraction

        rotor_lift_required = W - wing_lift

        cd_induced = cl ** 2 / (np.pi * AR * e) if (v > 0.1 and AR > 0) else 0.0
        cd_total = cd0 + cd_induced
        drag = q * S * cd_total if v > 0.1 else 0.0

        power_parasitic = drag * v

        load_factor = 1.0
        if v > 0.1 and wing_lift > 0:
            load_factor = wing_lift / W * wing_fraction + (1.0 - wing_fraction)

        feasible = (v <= vne) and (load_factor <= max_lf) and (rotor_lift_required >= 0)

        out = ModelOutput(
            values={
                "drag_N": drag,
                "lift_required_N": W,
                "wing_lift_N": wing_lift,
                "rotor_lift_required_N": rotor_lift_required,
                "power_parasitic_W": power_parasitic,
                "flight_mode_id": mode_id,
                "load_factor": load_factor,
                "aero_feasible": float(feasible),
            },
            units={
                "drag_N": "N", "lift_required_N": "N", "wing_lift_N": "N",
                "rotor_lift_required_N": "N", "power_parasitic_W": "W",
                "flight_mode_id": "1", "load_factor": "1", "aero_feasible": "1",
            },
            feasible=feasible,
        )
        if not feasible:
            if v > vne:
                out.warnings.append(f"Airspeed {v:.1f} m/s exceeds VNE {vne:.1f} m/s")
            if load_factor > max_lf:
                out.warnings.append(f"Load factor {load_factor:.2f} exceeds limit {max_lf:.1f}")
        return out
