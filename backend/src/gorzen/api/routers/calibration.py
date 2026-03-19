"""Calibration pipeline endpoints: ingest, status, missions."""

from __future__ import annotations

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from gorzen.calibration.calibration_missions import (
    ALL_CALIBRATION_MISSIONS,
    CalibrationMissionType,
)

router = APIRouter()


class CalibrationStatus(BaseModel):
    twin_id: str
    last_calibrated: str | None = None
    available_missions: list[str]
    posteriors_version: str | None = None
    data_coverage_pct: float = 0.0


@router.get("/{twin_id}/status", response_model=CalibrationStatus)
async def get_calibration_status(twin_id: str) -> CalibrationStatus:
    return CalibrationStatus(
        twin_id=twin_id,
        available_missions=[m.value for m in CalibrationMissionType],
    )


@router.get("/missions", response_model=list[dict])
async def list_calibration_missions() -> list[dict]:
    missions = []
    for mission_type, factory in ALL_CALIBRATION_MISSIONS.items():
        defn = factory()
        missions.append({
            "type": defn.mission_type.value,
            "name": defn.name,
            "description": defn.description,
            "estimated_duration_min": defn.estimated_duration_min,
            "calibrates_parameters": defn.calibrates_parameters,
            "n_steps": len(defn.steps),
        })
    return missions


@router.post("/ingest")
async def ingest_telemetry(file: UploadFile) -> dict:
    content = await file.read()
    return {
        "status": "received",
        "filename": file.filename,
        "size_bytes": len(content),
        "message": "Telemetry ingest queued for processing",
    }
