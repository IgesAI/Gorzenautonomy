"""Calibration pipeline endpoints: ingest, status, missions, battery life."""

from __future__ import annotations

import io

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from gorzen.calibration.battery_life import BatteryLifeModel, fit_battery_model
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


class BatteryCalibrateRequest(BaseModel):
    """CSV content with columns: flight_time_min, payload_kg, ground_speed_mps, headwind_mps."""

    csv_content: str


class BatteryCalibrateResponse(BaseModel):
    model: dict
    diagnostics: dict


@router.post("/battery/calibrate", response_model=BatteryCalibrateResponse)
async def calibrate_battery(req: BatteryCalibrateRequest) -> BatteryCalibrateResponse:
    """Fit battery life model from flight log CSV."""
    import pandas as pd

    df = pd.read_csv(io.StringIO(req.csv_content))
    required = ["flight_time_min", "payload_kg", "ground_speed_mps", "headwind_mps"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")

    model, diag = fit_battery_model(
        df["flight_time_min"].values,
        df["payload_kg"].values,
        df["ground_speed_mps"].values,
        df["headwind_mps"].values,
    )
    return BatteryCalibrateResponse(model=model.to_dict(), diagnostics=diag)


class BatteryEstimateRequest(BaseModel):
    model: dict  # from calibrate response
    payload_kg: float
    ground_speed_mps: float
    headwind_mps: float = 0.0
    voltage_per_cell: float | None = None  # if set, estimate remaining time


class BatteryEstimateResponse(BaseModel):
    total_time_min: float
    remaining_time_min: float | None = None
    soc_pct: float | None = None


@router.post("/battery/estimate", response_model=BatteryEstimateResponse)
async def estimate_battery(req: BatteryEstimateRequest) -> BatteryEstimateResponse:
    """Estimate flight time from calibrated battery model."""
    m = BatteryLifeModel.from_dict(req.model)
    total = m.predict_total_time_min(
        req.payload_kg, req.ground_speed_mps, req.headwind_mps
    )
    remaining = None
    soc_pct = None
    if req.voltage_per_cell is not None:
        remaining = m.predict_remaining_time_min(
            req.payload_kg,
            req.ground_speed_mps,
            req.headwind_mps,
            req.voltage_per_cell,
        )
        from gorzen.calibration.battery_life import soc_from_voltage_per_cell
        soc_pct = soc_from_voltage_per_cell(req.voltage_per_cell) * 100
    return BatteryEstimateResponse(
        total_time_min=total,
        remaining_time_min=remaining,
        soc_pct=soc_pct,
    )
