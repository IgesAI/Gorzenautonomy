"""Propulsion models: ICE engine, electric rotor, motor, ESC.

Covers both electric VTOL lift rotors and ICE cruise propulsion for
lift+cruise hybrid VTOL platforms like the VA-55/120/150 with Cobra AERO engines.
"""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel

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
        max_power_kw = params.get("max_power_kw", 2.2)
        max_rpm = params.get("max_power_rpm", 8350)
        bsfc = params.get("bsfc_cruise_g_kwh", 500.0)
        gen_cont_w = params.get("generator_output_w", 200.0)
        gen_int_w = params.get("generator_output_intermittent_w", 400.0)
        has_alt_comp = bool(params.get("altitude_compensation", 1))
        has_hybrid = bool(params.get("hybrid_boost_available", 1))
        hybrid_kw = params.get("hybrid_boost_power_kw", 0.5)

        alt_m = conditions.get("altitude_m", 0.0)
        temp_c = conditions.get("temperature_c", 20.0)
        power_demand_kw = conditions.get("cruise_power_demand_kw", 1.0)
        density_alt_ft = conditions.get("density_altitude_ft", alt_m * 3.281)

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
        fuel_density_kg_l = conditions.get("fuel_density_kg_l", 0.81)
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
        n_rotors = int(params.get("rotor_count", 4))
        D = params.get("rotor_diameter_m", 0.6)
        ct0 = params.get("prop_ct_static", 0.1)
        cp0 = params.get("prop_cp_static", 0.04)

        alt = conditions.get("altitude_m", 50.0)
        thrust_required_N = conditions.get("rotor_lift_required_N", 0.0)
        v_fwd = conditions.get("airspeed_ms", 0.0)

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
        kv = params.get("motor_kv", 400.0)
        R_m = params.get("motor_resistance_ohm", 0.05)
        kt = params.get("motor_kt", 0.024)

        rpm = conditions.get("rotor_rpm", 5000.0)
        torque_per_motor = conditions.get("rotor_torque_total_Nm", 0.1)
        n_rotors = int(conditions.get("rotor_count", 4))

        if n_rotors > 0 and torque_per_motor > 0:
            torque_per = torque_per_motor / n_rotors
        else:
            torque_per = 0.01

        I = torque_per / (kt + 1e-9)
        back_emf = rpm / (kv + 1e-9)
        V = back_emf + I * R_m
        P_elec = V * I * n_rotors
        P_mech = conditions.get("rotor_power_total_W", P_elec * 0.85)
        eff = P_mech / (P_elec + 1e-6) if P_elec > 1.0 else 0.0

        return ModelOutput(
            values={
                "motor_current_A": I * n_rotors,
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
        R_esc = params.get("esc_resistance_mohm", 3.0) / 1000.0
        sw_pct = params.get("esc_switching_loss_pct", 2.0) / 100.0

        I_total = conditions.get("motor_current_A", 10.0)
        P_motor = conditions.get("motor_power_elec_W", 200.0)

        conduction_loss = I_total ** 2 * R_esc
        switching_loss = P_motor * sw_pct
        esc_loss = conduction_loss + switching_loss

        compute_power = conditions.get("compute_power_W", 15.0)
        avionics_power = conditions.get("avionics_power_W", 10.0)
        total_elec = P_motor + esc_loss + compute_power + avionics_power

        return ModelOutput(
            values={
                "esc_loss_W": esc_loss,
                "total_electrical_power_W": total_elec,
            },
            units={"esc_loss_W": "W", "total_electrical_power_W": "W"},
        )
