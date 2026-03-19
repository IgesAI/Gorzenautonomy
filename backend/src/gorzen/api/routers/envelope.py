"""Envelope computation endpoints."""

from __future__ import annotations

import copy
from typing import Any

from fastapi import APIRouter, HTTPException

from gorzen.api.routers.twin import _twins
from gorzen.schemas.envelope import EnvelopeRequest, EnvelopeResponse
from gorzen.schemas.twin_graph import VehicleTwin
from gorzen.solver.envelope_solver import compute_envelope

router = APIRouter()

# mission_profile params from environment vs constraints (schema flattens these)
_MISSION_ENV_PARAMS = frozenset({
    "wind_model", "wind_speed_ms", "gust_intensity", "wind_direction_deg",
    "temperature_c", "pressure_hpa", "density_altitude_ft", "ambient_light_lux",
})
_MISSION_CONSTRAINT_PARAMS = frozenset({
    "min_gsd_cm_px", "max_blur_px", "min_identification_confidence",
    "fuel_reserve_pct", "battery_reserve_pct", "min_overlap_pct",
    "max_mission_duration_hr", "max_range_nmi",
})


def _coerce_value(val: Any, default_type: type = float) -> Any:
    """Coerce JSON value to proper type for deterministic model input.
    Handles nested {value: x} from schema param objects."""
    if val is None:
        return val
    if isinstance(val, dict) and "value" in val:
        val = val["value"]
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val) if default_type == float else val
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return val
    return val


def _apply_param_overrides(twin: VehicleTwin, overrides: dict[str, dict[str, Any]]) -> None:
    """Apply param_overrides to twin in-place. mission_profile params routed to environment/constraints.
    Values are coerced for deterministic model input. Iteration order is sorted for deterministic behavior."""
    for subsystem in sorted(overrides.keys()):
        params = overrides[subsystem]
        if not params:
            continue
        if subsystem == "mission_profile":
            env = twin.mission_profile.environment
            constraints = twin.mission_profile.constraints
            for name in sorted(params.keys()):
                val = params[name]
                if name == "mission_type":
                    twin.mission_profile.mission_type = str(val)
                elif name in _MISSION_ENV_PARAMS and hasattr(env, name):
                    getattr(env, name).value = _coerce_value(val)
                elif name in _MISSION_CONSTRAINT_PARAMS and hasattr(constraints, name):
                    getattr(constraints, name).value = _coerce_value(val)
        elif hasattr(twin, subsystem):
            config = getattr(twin, subsystem)
            for name in sorted(params.keys()):
                val = params[name]
                if hasattr(config, name):
                    attr = getattr(config, name)
                    if hasattr(attr, "value"):
                        attr.value = _coerce_value(val)
                    else:
                        setattr(config, name, _coerce_value(val))


@router.post("/default/envelope", response_model=EnvelopeResponse)
async def compute_default_envelope(request: EnvelopeRequest) -> EnvelopeResponse:
    """Compute envelope using default twin config, with optional param_overrides from frontend."""
    twin = VehicleTwin()
    if request.param_overrides:
        _apply_param_overrides(twin, request.param_overrides)
    return compute_envelope(
        twin,
        speed_range=request.speed_range_ms,
        altitude_range=request.altitude_range_m,
        grid_resolution=request.grid_resolution,
        uq_method=request.uq_method,
        mc_samples=request.mc_samples,
    )


@router.post("/{twin_id}/envelope", response_model=EnvelopeResponse)
async def compute_twin_envelope(twin_id: str, request: EnvelopeRequest) -> EnvelopeResponse:
    if twin_id not in _twins:
        raise HTTPException(status_code=404, detail="Twin not found")

    twin = copy.deepcopy(_twins[twin_id])
    if request.param_overrides:
        _apply_param_overrides(twin, request.param_overrides)
    return compute_envelope(
        twin,
        speed_range=request.speed_range_ms,
        altitude_range=request.altitude_range_m,
        grid_resolution=request.grid_resolution,
        uq_method=request.uq_method,
        mc_samples=request.mc_samples,
    )
