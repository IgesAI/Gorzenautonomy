"""PX4 parameter mapping service.

Maps Gorzen digital twin parameters to/from PX4 autopilot parameters.
Enables syncing twin configuration with real drone config.
"""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from typing import Any


def _safe_eval(expr: str) -> float:
    """Evaluate simple arithmetic expressions safely."""
    node = ast.parse(expr, mode="eval").body
    _ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
    }

    def _eval(n: ast.expr) -> float:
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _ops:
            return _ops[type(n.op)](_eval(n.left), _eval(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -_eval(n.operand)
        raise ValueError(f"Unsupported expression: {ast.dump(n)}")

    return _eval(node)


@dataclass
class ParamMapping:
    """Single mapping between a twin parameter and a PX4 parameter."""

    twin_subsystem: str
    twin_param: str
    px4_param: str
    px4_description: str
    transform_to_px4: str  # expression: {v} is twin value
    transform_from_px4: str  # expression: {v} is PX4 value
    px4_type: str = "float"  # float, int32
    px4_group: str = ""
    px4_min: float | None = None
    px4_max: float | None = None
    px4_unit: str = ""


# Comprehensive PX4 parameter mapping table
PX4_PARAM_MAP: list[ParamMapping] = [
    # --- Battery ---
    ParamMapping(
        twin_subsystem="energy",
        twin_param="cell_count_s",
        px4_param="BAT1_N_CELLS",
        px4_description="Number of battery cells in series",
        transform_to_px4="{v}",
        transform_from_px4="{v}",
        px4_type="int32",
        px4_group="Battery",
        px4_min=1,
        px4_max=16,
    ),
    ParamMapping(
        twin_subsystem="energy",
        twin_param="capacity_ah",
        px4_param="BAT1_CAPACITY",
        px4_description="Battery capacity in mAh",
        transform_to_px4="{v} * 1000",
        transform_from_px4="{v} / 1000",
        px4_group="Battery",
        px4_min=0,
        px4_max=100000,
        px4_unit="mAh",
    ),
    ParamMapping(
        twin_subsystem="energy",
        twin_param="internal_resistance_mohm",
        px4_param="BAT1_R_INTERNAL",
        px4_description="Internal resistance per cell",
        transform_to_px4="{v} / 1000",
        transform_from_px4="{v} * 1000",
        px4_group="Battery",
        px4_unit="Ohm",
    ),
    ParamMapping(
        twin_subsystem="energy",
        twin_param="nominal_voltage_v",
        px4_param="BAT1_V_CHARGED",
        px4_description="Full cell voltage × cells",
        transform_to_px4="{v} / {cell_count_s}",
        transform_from_px4="{v} * {cell_count_s}",
        px4_group="Battery",
        px4_min=3.0,
        px4_max=4.35,
        px4_unit="V",
    ),
    # --- Airframe ---
    ParamMapping(
        twin_subsystem="airframe",
        twin_param="mass_mtow_kg",
        px4_param="WEIGHT_GROSS",
        px4_description="Vehicle gross weight",
        transform_to_px4="{v}",
        transform_from_px4="{v}",
        px4_group="Airframe",
        px4_unit="kg",
    ),
    ParamMapping(
        twin_subsystem="airframe",
        twin_param="max_speed_kts",
        px4_param="FW_AIRSPD_MAX",
        px4_description="Maximum airspeed",
        transform_to_px4="{v} * 0.514444",
        transform_from_px4="{v} / 0.514444",
        px4_group="Fixed-wing",
        px4_unit="m/s",
    ),
    ParamMapping(
        twin_subsystem="airframe",
        twin_param="cruise_speed_kts",
        px4_param="FW_AIRSPD_TRIM",
        px4_description="Cruise/trim airspeed",
        transform_to_px4="{v} * 0.514444",
        transform_from_px4="{v} / 0.514444",
        px4_group="Fixed-wing",
        px4_unit="m/s",
    ),
    # --- Mission ---
    ParamMapping(
        twin_subsystem="mission_profile",
        twin_param="wind_speed_ms",
        px4_param="COM_WIND_MAX",
        px4_description="Max wind speed for auto modes",
        transform_to_px4="{v}",
        transform_from_px4="{v}",
        px4_group="Commander",
        px4_unit="m/s",
    ),
    ParamMapping(
        twin_subsystem="mission_profile",
        twin_param="battery_reserve_pct",
        px4_param="BAT_LOW_THR",
        px4_description="Low battery threshold",
        transform_to_px4="{v} / 100",
        transform_from_px4="{v} * 100",
        px4_group="Battery",
        px4_min=0,
        px4_max=1,
    ),
    # --- VTOL / Multicopter ---
    ParamMapping(
        twin_subsystem="lift_propulsion",
        twin_param="rotor_count",
        px4_param="CA_ROTOR_COUNT",
        px4_description="Number of rotors",
        transform_to_px4="{v}",
        transform_from_px4="{v}",
        px4_type="int32",
        px4_group="Control Allocation",
    ),
    # --- Avionics ---
    ParamMapping(
        twin_subsystem="avionics",
        twin_param="ekf_position_noise_m",
        px4_param="EKF2_GPS_P_NOISE",
        px4_description="GPS position noise",
        transform_to_px4="{v}",
        transform_from_px4="{v}",
        px4_group="EKF2",
        px4_unit="m",
    ),
    ParamMapping(
        twin_subsystem="avionics",
        twin_param="ekf_velocity_noise_ms",
        px4_param="EKF2_GPS_V_NOISE",
        px4_description="GPS velocity noise",
        transform_to_px4="{v}",
        transform_from_px4="{v}",
        px4_group="EKF2",
        px4_unit="m/s",
    ),
    ParamMapping(
        twin_subsystem="avionics",
        twin_param="baro_noise_m",
        px4_param="EKF2_BARO_NOISE",
        px4_description="Barometer noise",
        transform_to_px4="{v}",
        transform_from_px4="{v}",
        px4_group="EKF2",
        px4_unit="m",
    ),
    ParamMapping(
        twin_subsystem="avionics",
        twin_param="imu_accel_noise_mg",
        px4_param="EKF2_ACC_NOISE",
        px4_description="Accelerometer noise density",
        transform_to_px4="{v} * 0.00981",
        transform_from_px4="{v} / 0.00981",
        px4_group="EKF2",
        px4_unit="m/s²",
    ),
    ParamMapping(
        twin_subsystem="avionics",
        twin_param="imu_gyro_noise_dps",
        px4_param="EKF2_GYR_NOISE",
        px4_description="Gyroscope noise density",
        transform_to_px4="{v} * 0.01745",
        transform_from_px4="{v} / 0.01745",
        px4_group="EKF2",
        px4_unit="rad/s",
    ),
    # --- Comms ---
    ParamMapping(
        twin_subsystem="comms",
        twin_param="tx_power_dbm",
        px4_param="MAV_RADIO_TOUT",
        px4_description="Radio timeout (related)",
        transform_to_px4="{v}",
        transform_from_px4="{v}",
        px4_group="MAVLink",
    ),
    # --- Geofence / Safety ---
    ParamMapping(
        twin_subsystem="airframe",
        twin_param="service_ceiling_ft",
        px4_param="GF_MAX_VER_DIST",
        px4_description="Geofence max vertical distance",
        transform_to_px4="{v} * 0.3048",
        transform_from_px4="{v} / 0.3048",
        px4_group="Geofence",
        px4_unit="m",
    ),
]


def get_param_map() -> list[dict[str, Any]]:
    """Get the full parameter mapping table as JSON-serializable dicts."""
    return [
        {
            "twin_subsystem": m.twin_subsystem,
            "twin_param": m.twin_param,
            "px4_param": m.px4_param,
            "px4_description": m.px4_description,
            "px4_group": m.px4_group,
            "px4_unit": m.px4_unit,
            "px4_type": m.px4_type,
            "px4_min": m.px4_min,
            "px4_max": m.px4_max,
        }
        for m in PX4_PARAM_MAP
    ]


def twin_to_px4(twin_params: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Convert twin parameters to PX4 parameter values.

    Args:
        twin_params: {subsystem: {param_name: value}}

    Returns:
        {px4_param_name: value}
    """
    result: dict[str, Any] = {}
    cell_count_s = twin_params.get("energy", {}).get("cell_count_s", 12)

    for m in PX4_PARAM_MAP:
        val = twin_params.get(m.twin_subsystem, {}).get(m.twin_param)
        if val is None:
            continue

        # Simple expression eval with variable substitution
        expr = m.transform_to_px4.replace("{v}", str(float(val)))
        expr = expr.replace("{cell_count_s}", str(float(cell_count_s)))
        try:
            px4_val = _safe_eval(expr)
            if m.px4_type == "int32":
                px4_val = int(round(px4_val))
            result[m.px4_param] = px4_val
        except Exception:
            pass

    return result


def px4_to_twin(px4_params: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Convert PX4 parameters back to twin parameter values.

    Args:
        px4_params: {px4_param_name: value}

    Returns:
        {subsystem: {param_name: value}}
    """
    result: dict[str, dict[str, Any]] = {}
    cell_count_s = 12
    # Try to get cell count first
    if "BAT1_N_CELLS" in px4_params:
        cell_count_s = int(px4_params["BAT1_N_CELLS"])

    for m in PX4_PARAM_MAP:
        val = px4_params.get(m.px4_param)
        if val is None:
            continue

        expr = m.transform_from_px4.replace("{v}", str(float(val)))
        expr = expr.replace("{cell_count_s}", str(float(cell_count_s)))
        try:
            twin_val = _safe_eval(expr)
            if m.twin_subsystem not in result:
                result[m.twin_subsystem] = {}
            result[m.twin_subsystem][m.twin_param] = twin_val
        except Exception:
            pass

    return result


def get_px4_groups() -> list[dict[str, Any]]:
    """Get parameters organized by PX4 group."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for m in PX4_PARAM_MAP:
        g = m.px4_group or "Uncategorized"
        if g not in groups:
            groups[g] = []
        groups[g].append(
            {
                "px4_param": m.px4_param,
                "twin_param": f"{m.twin_subsystem}.{m.twin_param}",
                "description": m.px4_description,
                "unit": m.px4_unit,
            }
        )
    return [{"group": k, "params": v} for k, v in sorted(groups.items())]
