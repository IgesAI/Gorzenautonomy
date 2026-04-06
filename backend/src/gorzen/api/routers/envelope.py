"""Envelope computation endpoints."""

from __future__ import annotations

import copy
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db import twin_repo
from gorzen.db.session import get_session
from gorzen.schemas.envelope import EnvelopeRequest, EnvelopeResponse
from gorzen.schemas.twin_graph import VehicleTwin
from gorzen.solver.envelope_solver import compute_envelope, estimate_endurance_budget_minutes

router = APIRouter()

_MISSION_ENV_PARAMS = frozenset(
    {
        "wind_model",
        "wind_speed_ms",
        "gust_intensity",
        "wind_direction_deg",
        "temperature_c",
        "pressure_hpa",
        "density_altitude_ft",
        "ambient_light_lux",
    }
)
_MISSION_CONSTRAINT_PARAMS = frozenset(
    {
        "min_gsd_cm_px",
        "target_feature_mm",
        "max_blur_px",
        "min_identification_confidence",
        "fuel_reserve_pct",
        "battery_reserve_pct",
        "min_overlap_pct",
        "max_mission_duration_hr",
        "max_range_nmi",
    }
)


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
        return float(val) if default_type is float else val
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return val
    return val


def _apply_param_overrides(twin: VehicleTwin, overrides: dict[str, dict[str, Any]]) -> list[str]:
    """Apply param_overrides to twin in-place. mission_profile params routed to environment/constraints.

    Returns a list of ignored override keys (``subsystem.name``) for operator visibility.
    """
    ignored: list[str] = []
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
                else:
                    ignored.append(f"mission_profile.{name}")
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
                else:
                    ignored.append(f"{subsystem}.{name}")
        else:
            for name in sorted(params.keys()):
                ignored.append(f"{subsystem}.{name}")
    return ignored


def _merge_override_warnings(response: EnvelopeResponse, ignored: list[str]) -> EnvelopeResponse:
    if not ignored:
        return response
    extra = [f"param_overrides ignored: {k}" for k in ignored]
    return response.model_copy(
        update={
            "param_override_warnings": list(ignored),
            "warnings": list(response.warnings) + extra,
        }
    )


@router.post("/default/envelope", response_model=EnvelopeResponse)
async def compute_default_envelope(request: EnvelopeRequest) -> EnvelopeResponse:
    """Compute envelope using default twin config, with optional param_overrides from frontend."""
    twin = VehicleTwin()
    ignored: list[str] = []
    if request.param_overrides:
        ignored = _apply_param_overrides(twin, request.param_overrides)
    out = compute_envelope(
        twin,
        speed_range=request.speed_range_ms,
        altitude_range=request.altitude_range_m,
        grid_resolution=request.grid_resolution,
        uq_method=request.uq_method,
        mc_samples=request.mc_samples,
    )
    return _merge_override_warnings(out, ignored)


@router.get("/{twin_id}/endurance-preview")
async def twin_endurance_preview(
    twin_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    speed_ms: float = Query(15.0, ge=0.5, le=80.0),
    altitude_m: float = Query(50.0, ge=0.0, le=12000.0),
) -> dict[str, float]:
    """Approximate electrical vs fuel endurance (minutes) from the physics chain at one flight point."""
    if twin_id == "default":
        twin = VehicleTwin()
    else:
        twin = await twin_repo.get_vehicle_twin(session, twin_id)
        if twin is None:
            raise HTTPException(status_code=404, detail="Twin not found")
    return estimate_endurance_budget_minutes(twin, speed_ms=speed_ms, altitude_m=altitude_m)


@router.post("/{twin_id}/envelope", response_model=EnvelopeResponse)
async def compute_twin_envelope(
    twin_id: str,
    request: EnvelopeRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EnvelopeResponse:
    twin_model = await twin_repo.get_vehicle_twin(session, twin_id)
    if twin_model is None:
        raise HTTPException(status_code=404, detail="Twin not found")

    twin = copy.deepcopy(twin_model)
    ignored: list[str] = []
    if request.param_overrides:
        ignored = _apply_param_overrides(twin, request.param_overrides)
    out = compute_envelope(
        twin,
        speed_range=request.speed_range_ms,
        altitude_range=request.altitude_range_m,
        grid_resolution=request.grid_resolution,
        uq_method=request.uq_method,
        mc_samples=request.mc_samples,
    )
    return _merge_override_warnings(out, ignored)
