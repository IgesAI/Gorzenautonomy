"""Fuel system model: tank capacity, burn rate, endurance, fuel weight reduction.

Models fuel consumption for ICE-powered VTOL platforms. Fuel weight decreases
during flight, affecting CG and total vehicle weight dynamically.
"""

from __future__ import annotations


from gorzen.models.base import ModelOutput, SubsystemModel
from gorzen.validation.parameter_validator import require_param


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
        if "fuel_type" not in params or params["fuel_type"] is None:
            raise ValueError(
                "INSUFFICIENT_DATA: 'fuel_type' is required but missing"
                " (context: FuelSystemModel)"
            )
        str(params["fuel_type"])
        density = require_param(params, "fuel_density_kg_l", "FuelSystemModel")
        require_param(params, "tank_capacity_l", "FuelSystemModel")
        tank_kg = require_param(params, "tank_capacity_kg", "FuelSystemModel")
        usable_frac = require_param(params, "usable_fuel_pct", "FuelSystemModel") / 100.0
        reserve_pct = require_param(params, "fuel_reserve_pct", "FuelSystemModel") / 100.0

        fuel_flow_g_hr = require_param(conditions, "fuel_flow_rate_g_hr", "FuelSystemModel")
        elapsed_hr = require_param(conditions, "mission_elapsed_hr", "FuelSystemModel")
        cruise_speed_kts = require_param(conditions, "cruise_speed_kts", "FuelSystemModel")
        mass_empty = require_param(conditions, "mass_empty_kg", "FuelSystemModel")
        payload_mass = require_param(conditions, "payload_mass_kg", "FuelSystemModel")

        # Fuel burned so far
        fuel_burned_kg = fuel_flow_g_hr * elapsed_hr / 1000.0
        fuel_remaining_kg = max(tank_kg - fuel_burned_kg, 0.0)
        fuel_remaining_l = fuel_remaining_kg / density
        fuel_remaining_pct = (fuel_remaining_kg / (tank_kg + 1e-9)) * 100.0

        # Usable fuel accounts for tank geometry (not all fuel is accessible)
        max_usable_kg = tank_kg * usable_frac
        reserve_kg = tank_kg * reserve_pct
        usable_remaining = max(min(fuel_remaining_kg, max_usable_kg) - reserve_kg, 0.0)

        warnings: list[str] = []

        # Endurance from remaining fuel
        if fuel_flow_g_hr > 0:
            endurance_hr = (usable_remaining * 1000.0) / fuel_flow_g_hr
        else:
            endurance_hr = 0.0
            warnings.append("fuel_flow_rate_g_hr is zero; endurance cannot be computed")

        # Range from remaining fuel
        fuel_range_nmi = endurance_hr * cruise_speed_kts

        # Dynamic weight: vehicle gets lighter as fuel burns
        current_mass = mass_empty + payload_mass + fuel_remaining_kg
        weight_reduction = fuel_burned_kg

        feasible = fuel_remaining_kg > reserve_kg
        if not feasible:
            warnings.append("Fuel remaining below reserve threshold")

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
        out.warnings.extend(warnings)
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
        gen_cont = require_param(params, "generator_output_w", "GeneratorModel")
        gen_int = require_param(params, "generator_output_intermittent_w", "GeneratorModel")
        charge_rate = require_param(params, "generator_charge_rate_w", "GeneratorModel")
        has_hybrid = bool(require_param(params, "hybrid_boost_available", "GeneratorModel"))

        elec_demand = require_param(conditions, "total_electrical_power_W", "GeneratorModel")
        engine_load_pct = require_param(conditions, "throttle_pct", "GeneratorModel") / 100.0
        in_vtol = require_param(conditions, "flight_mode_id", "GeneratorModel") < 1.5
        battery_soc = require_param(conditions, "soc_pct", "GeneratorModel")

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
