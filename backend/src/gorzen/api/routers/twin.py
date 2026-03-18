"""CRUD endpoints for vehicle twin configurations."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException

from gorzen.schemas.twin_graph import VehicleTwin

router = APIRouter()

# In-memory store (replace with DB in production)
_twins: dict[str, VehicleTwin] = {}

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

    # Build the mission_profile subsystem from its nested structure
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
async def create_twin(twin: VehicleTwin) -> VehicleTwin:
    twin = twin.with_hash()
    _twins[str(twin.twin_id)] = twin
    return twin


@router.get("/", response_model=list[VehicleTwin])
async def list_twins() -> list[VehicleTwin]:
    return list(_twins.values())


@router.get("/{twin_id}", response_model=VehicleTwin)
async def get_twin(twin_id: str) -> VehicleTwin:
    if twin_id not in _twins:
        raise HTTPException(status_code=404, detail="Twin not found")
    return _twins[twin_id]


@router.put("/{twin_id}", response_model=VehicleTwin)
async def update_twin(twin_id: str, twin: VehicleTwin) -> VehicleTwin:
    if twin_id not in _twins:
        raise HTTPException(status_code=404, detail="Twin not found")
    twin.twin_id = UUID(twin_id)
    twin = twin.with_hash()
    _twins[twin_id] = twin
    return twin


@router.delete("/{twin_id}")
async def delete_twin(twin_id: str) -> dict[str, str]:
    if twin_id not in _twins:
        raise HTTPException(status_code=404, detail="Twin not found")
    del _twins[twin_id]
    return {"status": "deleted"}
