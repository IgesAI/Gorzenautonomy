"""Propulsion models: ICE engine, electric rotor, motor, ESC.

Covers both electric VTOL lift rotors and ICE cruise propulsion for
lift+cruise hybrid VTOL platforms like the VA-55/120/150 with Cobra AERO engines.
"""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel
from gorzen.validation.parameter_validator import require_param

G = 9.81
RHO_0 = 1.225


def isa_density(altitude_m: float) -> float:
    T = 288.15 - 0.0065 * altitude_m
    return RHO_0 * (T / 288.15) ** 4.2561


# ---------------------------------------------------------------------------
# ICE engine model (2-stroke singles/triples, altitude-compensated)
# ---------------------------------------------------------------------------

class ICEEngineModel(SubsystemModel):
    """Internal combustion engine model with BSFC-based fuel consumption.

    Covers 2-stroke single (A33N/A33HF) through inline triples (A99HF/A99S).
    Includes altitude derating, temperature effects, and generator output.
    """

    def parameter_names(self) -> list[str]:
        return [
            "engine_type", "displacement_cc", "max_power_kw", "max_power_rpm",
            "bsfc_cruise_g_kwh", "cooling_type", "altitude_compensation",
            "generator_output_w", "generator_output_intermittent_w",
            "hybrid_boost_available", "hybrid_boost_power_kw",
            "preheat_required", "preheat_time_min", "preheat_power_w",
        ]

    def state_names(self) -> list[str]:
        return ["cht_c", "mat_c", "rpm", "throttle_pct"]

    def output_names(self) -> list[str]:
        return [
            "engine_power_available_kw", "engine_power_required_kw",
            "fuel_flow_rate_g_hr", "fuel_flow_rate_l_hr",
            "engine_rpm", "throttle_pct",
            "generator_power_w", "cht_estimated_c",
            "engine_feasible",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        max_power_kw = require_param(params, "max_power_kw", "ICEEngineModel")
        max_rpm = require_param(params, "max_power_rpm", "ICEEngineModel")
        bsfc = require_param(params, "bsfc_cruise_g_kwh", "ICEEngineModel")
        gen_cont_w = require_param(params, "generator_output_w", "ICEEngineModel")
        has_alt_comp = bool(require_param(params, "altitude_compensation", "ICEEngineModel"))
        has_hybrid = bool(require_param(params, "hybrid_boost_available", "ICEEngineModel"))
        hybrid_kw = require_param(params, "hybrid_boost_power_kw", "ICEEngineModel")

        require_param(conditions, "altitude_m", "ICEEngineModel")
        temp_c = require_param(conditions, "temperature_c", "ICEEngineModel")
        power_demand_kw = require_param(conditions, "cruise_power_demand_kw", "ICEEngineModel")
        density_alt_ft = require_param(conditions, "density_altitude_ft", "ICEEngineModel")

        # Altitude derating: ~3% power loss per 1000 ft for normally aspirated
        # With EFI altitude compensation, reduce loss to ~1.5% per 1000 ft
        derate_per_1000ft = 0.015 if has_alt_comp else 0.03
        alt_factor = max(1.0 - derate_per_1000ft * (density_alt_ft / 1000.0), 0.3)

        # Temperature derating: hot air = less dense
        temp_factor = 1.0
        if temp_c > 30:
            temp_factor = max(1.0 - (temp_c - 30) * 0.005, 0.8)

        available_kw = max_power_kw * alt_factor * temp_factor
        if has_hybrid:
            available_kw += hybrid_kw

        # Throttle and RPM estimation
        throttle = min(power_demand_kw / (available_kw + 1e-6), 1.0)
        rpm = max_rpm * (0.4 + 0.6 * throttle)

        # Fuel consumption: BSFC is g/kW-hr at cruise
        # At part-throttle, BSFC degrades slightly
        bsfc_actual = bsfc * (1.0 + 0.15 * (1.0 - throttle))
        actual_power = min(power_demand_kw, available_kw)
        fuel_flow_g_hr = bsfc_actual * actual_power
        fuel_density_kg_l = require_param(conditions, "fuel_density_kg_l", "ICEEngineModel")
        fuel_flow_l_hr = fuel_flow_g_hr / (fuel_density_kg_l * 1000.0)

        # Generator output (reduced if engine is near max load)
        gen_headroom = max(available_kw - actual_power, 0)
        gen_power_available = min(gen_cont_w, gen_headroom * 1000.0 * 0.8)

        # CHT estimate (simplified thermal model)
        ambient = temp_c
        cht = ambient + 80 + 60 * throttle
        cooling = params.get("cooling_type", "air_cooled")
        if str(cooling) == "liquid_cooled":
            cht = min(cht, ambient + 95)

        feasible = actual_power >= power_demand_kw * 0.95

        return ModelOutput(
            values={
                "engine_power_available_kw": available_kw,
                "engine_power_required_kw": actual_power,
                "fuel_flow_rate_g_hr": fuel_flow_g_hr,
                "fuel_flow_rate_l_hr": fuel_flow_l_hr,
                "engine_rpm": rpm,
                "throttle_pct": throttle * 100,
                "generator_power_w": gen_power_available,
                "cht_estimated_c": cht,
                "engine_feasible": float(feasible),
            },
            units={
                "engine_power_available_kw": "kW", "engine_power_required_kw": "kW",
                "fuel_flow_rate_g_hr": "g/hr", "fuel_flow_rate_l_hr": "L/hr",
                "engine_rpm": "rpm", "throttle_pct": "%",
                "generator_power_w": "W", "cht_estimated_c": "degC",
                "engine_feasible": "1",
            },
            feasible=feasible,
        )


# ---------------------------------------------------------------------------
# Electric rotor model (VTOL lift motors, same as before but with ICE context)
# ---------------------------------------------------------------------------

class RotorModel(SubsystemModel):
    """BET-based rotor thrust/torque model for electric VTOL lift motors."""

    def parameter_names(self) -> list[str]:
        return [
            "rotor_count", "rotor_diameter_m", "blade_count",
            "prop_ct_static", "prop_cp_static",
        ]

    def state_names(self) -> list[str]:
        return ["rpm"]

    def output_names(self) -> list[str]:
        return [
            "rotor_thrust_total_N", "rotor_torque_total_Nm",
            "rotor_power_total_W", "rotor_rpm", "rotor_efficiency",
            "thrust_available_N",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        n_rotors = int(require_param(params, "rotor_count", "RotorModel"))
        D = require_param(params, "rotor_diameter_m", "RotorModel")
        ct0 = require_param(params, "prop_ct_static", "RotorModel")
        cp0 = require_param(params, "prop_cp_static", "RotorModel")

        alt = require_param(conditions, "altitude_m", "RotorModel")
        thrust_required_N = require_param(conditions, "rotor_lift_required_N", "RotorModel")
        v_fwd = require_param(conditions, "airspeed_ms", "RotorModel")

        # Use Environment model's air_density when available (pressure/temp-corrected)
        rho = conditions.get("air_density_kgm3")
        if rho is None or rho <= 0:
            rho = isa_density(alt)
        R = D / 2.0
        A_disk = np.pi * R ** 2

        thrust_per_rotor = max(thrust_required_N / n_rotors, 0.01)

        n_rps = np.sqrt(thrust_per_rotor / (ct0 * rho * D ** 4 + 1e-12))
        rpm = n_rps * 60.0

        v_tip = n_rps * np.pi * D
        mu = v_fwd / (v_tip + 1e-6) if v_tip > 0.1 else 0.0
        ct_effective = ct0 * (1.0 - 0.3 * mu ** 2)
        cp_effective = cp0 * (1.0 + 0.5 * mu ** 2)

        thrust_actual = ct_effective * rho * n_rps ** 2 * D ** 4 * n_rotors
        torque_per = cp_effective * rho * n_rps ** 2 * D ** 5 / (2 * np.pi)
        torque_total = torque_per * n_rotors
        power_total = cp_effective * rho * n_rps ** 3 * D ** 5 * n_rotors

        rpm_max = 12000.0
        n_max = rpm_max / 60.0
        thrust_available = ct0 * rho * n_max ** 2 * D ** 4 * n_rotors

        efficiency = (thrust_actual * (thrust_actual / (2 * rho * A_disk * n_rotors + 1e-6)) ** 0.5) / (power_total + 1e-6) if power_total > 1.0 else 0.0

        return ModelOutput(
            values={
                "rotor_thrust_total_N": thrust_actual,
                "rotor_torque_total_Nm": torque_total,
                "rotor_power_total_W": power_total,
                "rotor_rpm": rpm,
                "rotor_efficiency": min(efficiency, 1.0),
                "thrust_available_N": thrust_available,
            },
            units={
                "rotor_thrust_total_N": "N", "rotor_torque_total_Nm": "N.m",
                "rotor_power_total_W": "W", "rotor_rpm": "rpm",
                "rotor_efficiency": "1", "thrust_available_N": "N",
            },
        )


class MotorElectricalModel(SubsystemModel):
    """BLDC motor: Kv/Kt, winding resistance, efficiency map."""

    def parameter_names(self) -> list[str]:
        return ["motor_kv", "motor_resistance_ohm", "motor_kt"]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return ["motor_current_A", "motor_voltage_V", "motor_power_elec_W", "motor_efficiency"]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        kv = require_param(params, "motor_kv", "MotorElectricalModel")
        R_m = require_param(params, "motor_resistance_ohm", "MotorElectricalModel")
        kt = require_param(params, "motor_kt", "MotorElectricalModel")

        rpm = require_param(conditions, "rotor_rpm", "MotorElectricalModel")
        torque_per_motor = require_param(conditions, "rotor_torque_total_Nm", "MotorElectricalModel")
        n_rotors = int(require_param(conditions, "rotor_count", "MotorElectricalModel"))

        if n_rotors > 0 and torque_per_motor > 0:
            torque_per = torque_per_motor / n_rotors
        else:
            torque_per = 0.01

        current_A = torque_per / (kt + 1e-9)
        back_emf = rpm / (kv + 1e-9)
        V = back_emf + current_A * R_m
        P_elec = V * current_A * n_rotors
        P_mech = require_param(conditions, "rotor_power_total_W", "MotorElectricalModel")
        eff = P_mech / (P_elec + 1e-6) if P_elec > 1.0 else 0.0

        return ModelOutput(
            values={
                "motor_current_A": current_A * n_rotors,
                "motor_voltage_V": V,
                "motor_power_elec_W": P_elec,
                "motor_efficiency": min(eff, 1.0),
            },
            units={
                "motor_current_A": "A", "motor_voltage_V": "V",
                "motor_power_elec_W": "W", "motor_efficiency": "1",
            },
        )


class ESCLossModel(SubsystemModel):
    """ESC conduction and switching losses."""

    def parameter_names(self) -> list[str]:
        return ["esc_resistance_mohm", "esc_switching_loss_pct"]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return ["esc_loss_W", "total_electrical_power_W"]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        R_esc = require_param(params, "esc_resistance_mohm", "ESCLossModel") / 1000.0
        sw_pct = require_param(params, "esc_switching_loss_pct", "ESCLossModel") / 100.0

        I_total = require_param(conditions, "motor_current_A", "ESCLossModel")
        P_motor = require_param(conditions, "motor_power_elec_W", "ESCLossModel")

        conduction_loss = I_total ** 2 * R_esc
        switching_loss = P_motor * sw_pct
        esc_loss = conduction_loss + switching_loss

        compute_power = require_param(conditions, "compute_power_W", "ESCLossModel")
        avionics_power = require_param(conditions, "avionics_power_W", "ESCLossModel")
        total_elec = P_motor + esc_loss + compute_power + avionics_power

        return ModelOutput(
            values={
                "esc_loss_W": esc_loss,
                "total_electrical_power_W": total_elec,
            },
            units={"esc_loss_W": "W", "total_electrical_power_W": "W"},
        )
