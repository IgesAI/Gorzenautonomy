"""CRUD endpoints for vehicle twin configurations."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db import audit_repo, twin_repo
from gorzen.db.session import get_session
from gorzen.schemas.twin_graph import VehicleTwin

router = APIRouter()

SUBSYSTEM_KEYS = [
    "airframe", "lift_propulsion", "cruise_propulsion", "fuel_system",
    "energy", "avionics", "compute", "comms", "payload", "ai_model",
]

SUBSYSTEM_META: dict[str, dict[str, str]] = {
    "airframe": {"label": "Airframe", "description": "Airframe dimensions, mass properties, aero coefficients, and operational limits"},
    "cruise_propulsion": {"label": "Engine / Cruise", "description": "ICE engine configuration, EFI, generator, and hybrid power management"},
    "fuel_system": {"label": "Fuel System", "description": "Fuel type, tank capacity, consumption model, and reserve policy"},
    "lift_propulsion": {"label": "VTOL Lift Motors", "description": "Electric VTOL lift motors, rotors, and ESC configuration"},
    "energy": {"label": "Battery / Electrical", "description": "Battery pack for VTOL motors and avionics, generator charging"},
    "avionics": {"label": "Avionics", "description": "Autopilot, GPS/RTK, IMU, and navigation filter configuration"},
    "compute": {"label": "Compute", "description": "Onboard SoC, accelerator, thermal throttling, and inference performance"},
    "comms": {"label": "Communications", "description": "MANET, SATCOM, link budget, and QoS requirements"},
    "payload": {"label": "Payload", "description": "Camera, IR sensor, gimbal, encoding, and special payload capabilities"},
    "ai_model": {"label": "AI Models", "description": "Onboard detection/classification model, runtime, and degradation curves"},
    "mission_profile": {"label": "Mission Profile", "description": "Environment conditions, mission constraints, and perception requirements"},
}


def _default_twin() -> VehicleTwin:
    return VehicleTwin()


@router.get("/schema", response_model=dict[str, Any])
async def get_twin_schema() -> dict[str, Any]:
    """Return the full default twin config with all parameter metadata.

    This is the single source of truth the frontend uses to build forms.
    Every subsystem is returned with its TypedParameter fields (value, units,
    constraints, ui_hints, uncertainty, provenance).
    """
    twin = _default_twin()
    dump = twin.model_dump()

    mp = dump.pop("mission_profile", {})
    env_params = mp.get("environment", {})
    constraint_params = mp.get("constraints", {})
    mission_profile_flat: dict[str, Any] = {}
    mission_profile_flat["mission_type"] = {
        "value": mp.get("mission_type", "isr"),
        "units": "",
        "ui_hints": {"display_name": "Mission Type", "group": "general", "advanced": False, "control_type": "text_input"},
    }
    for k, v in env_params.items():
        mission_profile_flat[k] = v
    for k, v in constraint_params.items():
        mission_profile_flat[k] = v

    subsystems: dict[str, Any] = {}
    for key in SUBSYSTEM_KEYS:
        meta = SUBSYSTEM_META.get(key, {"label": key, "description": ""})
        subsystems[key] = {
            "label": meta["label"],
            "description": meta["description"],
            "parameters": dump.get(key, {}),
        }

    subsystems["mission_profile"] = {
        "label": SUBSYSTEM_META["mission_profile"]["label"],
        "description": SUBSYSTEM_META["mission_profile"]["description"],
        "parameters": mission_profile_flat,
    }

    return {
        "subsystems": subsystems,
        "twin_id": str(twin.twin_id),
        "version": dump.get("version", {}),
    }


@router.post("/", response_model=VehicleTwin)
async def create_twin(
    twin: VehicleTwin,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VehicleTwin:
    existing = await twin_repo.get_vehicle_twin(session, str(twin.twin_id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Twin ID already exists — use PUT to update")
    result = await twin_repo.upsert_vehicle_twin(session, twin)
    await audit_repo.record_event(
        session,
        event_type="twin.created",
        twin_id=result.twin_id,
        payload={"name": result.name},
    )
    return result


@router.get("/", response_model=list[VehicleTwin])
async def list_twins(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[VehicleTwin]:
    return await twin_repo.list_vehicle_twins(session)


@router.get("/{twin_id}", response_model=VehicleTwin)
async def get_twin(
    twin_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VehicleTwin:
    twin = await twin_repo.get_vehicle_twin(session, twin_id)
    if twin is None:
        raise HTTPException(status_code=404, detail="Twin not found")
    return twin


@router.put("/{twin_id}", response_model=VehicleTwin)
async def update_twin(
    twin_id: str,
    twin: VehicleTwin,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VehicleTwin:
    try:
        twin.twin_id = UUID(twin_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid twin ID") from None
    existing = await twin_repo.get_vehicle_twin(session, twin_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Twin not found")
    twin = twin.with_hash()
    result = await twin_repo.upsert_vehicle_twin(session, twin)
    await audit_repo.record_event(
        session,
        event_type="twin.updated",
        twin_id=result.twin_id,
        payload={"name": result.name},
    )
    return result


@router.delete("/{twin_id}")
async def delete_twin(
    twin_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    ok = await twin_repo.delete_vehicle_twin(session, twin_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Twin not found")
    try:
        uid = UUID(twin_id)
    except ValueError:
        uid = None
    await audit_repo.record_event(
        session,
        event_type="twin.deleted",
        twin_id=uid,
        payload={"twin_id": twin_id},
    )
    return {"status": "deleted"}
