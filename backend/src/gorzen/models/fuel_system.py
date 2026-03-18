"""Fuel system model: tank capacity, burn rate, endurance, fuel weight reduction.

Models fuel consumption for ICE-powered VTOL platforms. Fuel weight decreases
during flight, affecting CG and total vehicle weight dynamically.
"""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel


# Fuel density reference values (kg/L at 15C)
FUEL_DENSITIES = {
    "gasoline": 0.72,
    "jp5": 0.81,
    "jp8": 0.80,
    "jet_a": 0.81,
    "vp_heavy_fuel": 0.82,
    "avgas": 0.72,
}


class FuelSystemModel(SubsystemModel):
    """Models fuel state, consumption rate, and endurance from fuel.

    Accounts for:
    - Fuel type density
    - Usable fuel fraction
    - Reserve policy
    - Weight reduction during flight (affects vehicle dynamics)
    - BSFC-based fuel flow from ICE engine
    """

    def parameter_names(self) -> list[str]:
        return [
            "fuel_type", "fuel_density_kg_l", "tank_capacity_l",
            "tank_capacity_kg", "usable_fuel_pct", "fuel_reserve_pct",
            "premix_ratio",
        ]

    def state_names(self) -> list[str]:
        return ["fuel_remaining_kg", "fuel_burned_kg"]

    def output_names(self) -> list[str]:
        return [
            "fuel_remaining_kg", "fuel_remaining_l", "fuel_remaining_pct",
            "fuel_endurance_hr", "fuel_range_nmi",
            "usable_fuel_remaining_kg", "reserve_fuel_kg",
            "weight_reduction_kg", "current_vehicle_mass_kg",
            "fuel_feasible",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        fuel_type = str(params.get("fuel_type", "jp5"))
        density = params.get("fuel_density_kg_l", FUEL_DENSITIES.get(fuel_type, 0.81))
        tank_l = params.get("tank_capacity_l", 18.5)
        tank_kg = params.get("tank_capacity_kg", tank_l * density)
        usable_pct = params.get("usable_fuel_pct", 95.0) / 100.0
        reserve_pct = params.get("fuel_reserve_pct", 15.0) / 100.0

        fuel_flow_g_hr = conditions.get("fuel_flow_rate_g_hr", 1000.0)
        fuel_flow_l_hr = conditions.get("fuel_flow_rate_l_hr", fuel_flow_g_hr / (density * 1000.0))
        elapsed_hr = conditions.get("mission_elapsed_hr", 0.0)
        cruise_speed_kts = conditions.get("cruise_speed_kts", 42.0)
        mass_empty = conditions.get("mass_empty_kg", 34.0)
        mass_mtow = conditions.get("mass_mtow_kg", 68.0)
        payload_mass = conditions.get("payload_mass_kg", 5.0)

        # Fuel burned so far
        fuel_burned_kg = fuel_flow_g_hr * elapsed_hr / 1000.0
        fuel_remaining_kg = max(tank_kg - fuel_burned_kg, 0.0)
        fuel_remaining_l = fuel_remaining_kg / density
        fuel_remaining_pct = (fuel_remaining_kg / (tank_kg + 1e-9)) * 100.0

        # Reserve fuel
        reserve_kg = tank_kg * reserve_pct
        usable_remaining = max(fuel_remaining_kg - reserve_kg, 0.0)

        # Endurance from remaining fuel
        if fuel_flow_g_hr > 0:
            endurance_hr = (usable_remaining * 1000.0) / fuel_flow_g_hr
        else:
            endurance_hr = 999.0

        # Range from remaining fuel
        fuel_range_nmi = endurance_hr * cruise_speed_kts

        # Dynamic weight: vehicle gets lighter as fuel burns
        current_mass = mass_empty + payload_mass + fuel_remaining_kg
        weight_reduction = fuel_burned_kg

        feasible = fuel_remaining_kg > reserve_kg

        out = ModelOutput(
            values={
                "fuel_remaining_kg": fuel_remaining_kg,
                "fuel_remaining_l": fuel_remaining_l,
                "fuel_remaining_pct": fuel_remaining_pct,
                "fuel_endurance_hr": endurance_hr,
                "fuel_range_nmi": fuel_range_nmi,
                "usable_fuel_remaining_kg": usable_remaining,
                "reserve_fuel_kg": reserve_kg,
                "weight_reduction_kg": weight_reduction,
                "current_vehicle_mass_kg": current_mass,
                "fuel_feasible": float(feasible),
            },
            units={
                "fuel_remaining_kg": "kg", "fuel_remaining_l": "L",
                "fuel_remaining_pct": "%",
                "fuel_endurance_hr": "hr", "fuel_range_nmi": "nmi",
                "usable_fuel_remaining_kg": "kg", "reserve_fuel_kg": "kg",
                "weight_reduction_kg": "kg", "current_vehicle_mass_kg": "kg",
                "fuel_feasible": "1",
            },
            feasible=feasible,
        )
        if not feasible:
            out.warnings.append("Fuel remaining below reserve threshold")
        return out


class GeneratorModel(SubsystemModel):
    """Generator / hybrid power management model.

    Models the electrical power available from the ICE engine's integrated
    starter-generator, including continuous vs intermittent ratings and
    battery charging capability.
    """

    def parameter_names(self) -> list[str]:
        return [
            "generator_output_w", "generator_output_intermittent_w",
            "generator_voltage_v", "generator_charge_rate_w",
            "hybrid_boost_available", "hybrid_boost_power_kw",
        ]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return [
            "generator_power_available_w", "generator_charging_w",
            "hybrid_boost_active", "total_electrical_budget_w",
            "electrical_surplus_w",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        gen_cont = params.get("generator_output_w", 200.0)
        gen_int = params.get("generator_output_intermittent_w", 400.0)
        gen_voltage = params.get("generator_voltage_v", 28.0)
        charge_rate = params.get("generator_charge_rate_w", 200.0)
        has_hybrid = bool(params.get("hybrid_boost_available", 1))
        hybrid_kw = params.get("hybrid_boost_power_kw", 0.5)

        elec_demand = conditions.get("total_electrical_power_W", 100.0)
        engine_load_pct = conditions.get("throttle_pct", 50.0) / 100.0
        in_vtol = conditions.get("flight_mode_id", 0.0) < 1.5  # hover or transition
        battery_soc = conditions.get("soc_pct", 80.0)

        # Generator available power depends on engine load headroom
        headroom = max(1.0 - engine_load_pct, 0.0)
        gen_available = gen_cont * headroom

        # During VTOL, generator may be at intermittent rating briefly
        if in_vtol:
            gen_available = min(gen_int, gen_available * 1.5)

        # Charging: only charge if surplus and battery below 95%
        charging = 0.0
        surplus = gen_available - elec_demand
        if surplus > 0 and battery_soc < 95.0:
            charging = min(surplus, charge_rate)

        # Hybrid boost: electric assist to ICE during climb/sprint
        boost_active = 0.0
        if has_hybrid and engine_load_pct > 0.85:
            boost_active = 1.0

        total_budget = gen_available + (battery_soc / 100.0 * 500.0)  # battery contribution estimate

        return ModelOutput(
            values={
                "generator_power_available_w": gen_available,
                "generator_charging_w": charging,
                "hybrid_boost_active": boost_active,
                "total_electrical_budget_w": total_budget,
                "electrical_surplus_w": max(surplus, 0),
            },
            units={
                "generator_power_available_w": "W",
                "generator_charging_w": "W",
                "hybrid_boost_active": "1",
                "total_electrical_budget_w": "W",
                "electrical_surplus_w": "W",
            },
        )
