"""Calibration pipeline endpoints: ingest, status, missions, battery life."""

from __future__ import annotations

import io
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.calibration.battery_life import BatteryLifeModel, fit_battery_model
from gorzen.calibration.calibration_missions import (
    ALL_CALIBRATION_MISSIONS,
    CalibrationMissionType,
)
from gorzen.db import calibration_repo
from gorzen.db.session import get_session

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


async def read_upload_with_limit(file: UploadFile, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"File too large (max {max_bytes // (1024 * 1024)} MB)")
    return data


router = APIRouter()


def _run_to_dict(row: object) -> dict[str, Any]:
    return {
        "id": str(row.id),  # type: ignore[attr-defined]
        "twin_id": str(row.twin_id),  # type: ignore[attr-defined]
        "mission_type": row.mission_type,  # type: ignore[attr-defined]
        "config_hash": row.config_hash,  # type: ignore[attr-defined]
        "regime": row.regime,  # type: ignore[attr-defined]
        "posteriors_json": row.posteriors_json,  # type: ignore[attr-defined]
        "n_observations": row.n_observations,  # type: ignore[attr-defined]
        "log_marginal_likelihood": row.log_marginal_likelihood,  # type: ignore[attr-defined]
        "log_ids": row.log_ids,  # type: ignore[attr-defined]
        "created_at": row.created_at.isoformat() if row.created_at else None,  # type: ignore[attr-defined]
    }


class CalibrationStatus(BaseModel):
    twin_id: str
    last_calibrated: str | None = None
    available_missions: list[str]
    posteriors_version: str | None = None
    data_coverage_pct: float = 0.0


class CalibrationRunCreate(BaseModel):
    twin_id: UUID
    mission_type: str
    config_hash: str
    regime: str = ""
    posteriors_json: dict[str, Any] = {}
    n_observations: int = 0
    log_marginal_likelihood: float = 0.0
    log_ids: list[str] = []


@router.get("/{twin_id}/status", response_model=CalibrationStatus)
async def get_calibration_status(
    twin_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CalibrationStatus:
    try:
        uid = UUID(twin_id)
    except ValueError:
        uid = None
    last_calibrated = None
    data_coverage = 0.0
    if uid is not None:
        runs = await calibration_repo.list_calibration_runs(session, twin_id=uid, limit=1)
        if runs:
            last_calibrated = runs[0].created_at.isoformat() if runs[0].created_at else None
            data_coverage = min(100.0, float(runs[0].n_observations))
    return CalibrationStatus(
        twin_id=twin_id,
        last_calibrated=last_calibrated,
        available_missions=[m.value for m in CalibrationMissionType],
        data_coverage_pct=data_coverage,
    )


@router.get("/missions", response_model=list[dict])
async def list_calibration_missions() -> list[dict]:
    missions = []
    for mission_type, factory in ALL_CALIBRATION_MISSIONS.items():
        defn = factory()
        missions.append(
            {
                "type": defn.mission_type.value,
                "name": defn.name,
                "description": defn.description,
                "estimated_duration_min": defn.estimated_duration_min,
                "calibrates_parameters": defn.calibrates_parameters,
                "n_steps": len(defn.steps),
            }
        )
    return missions


@router.get("/runs", response_model=list[dict[str, Any]])
async def list_runs(
    session: Annotated[AsyncSession, Depends(get_session)],
    twin_id: str | None = None,
    mission_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    uid: UUID | None = None
    if twin_id is not None:
        try:
            uid = UUID(twin_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid twin_id") from None
    rows = await calibration_repo.list_calibration_runs(
        session,
        twin_id=uid,
        mission_type=mission_type,
        limit=limit,
        offset=offset,
    )
    return [_run_to_dict(r) for r in rows]


@router.get("/runs/{run_id}")
async def get_run(
    run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    row = await calibration_repo.get_calibration_run(session, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Calibration run not found")
    return _run_to_dict(row)


@router.post("/runs", status_code=201)
async def create_run(
    body: CalibrationRunCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    row = await calibration_repo.create_calibration_run(
        session,
        twin_id=body.twin_id,
        mission_type=body.mission_type,
        config_hash=body.config_hash,
        regime=body.regime,
        posteriors_json=body.posteriors_json,
        n_observations=body.n_observations,
        log_marginal_likelihood=body.log_marginal_likelihood,
        log_ids=body.log_ids,
    )
    return _run_to_dict(row)


@router.delete("/runs/{run_id}")
async def delete_run(
    run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    ok = await calibration_repo.delete_calibration_run(session, run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Calibration run not found")
    return {"status": "deleted"}


@router.post("/ingest")
async def ingest_telemetry(file: UploadFile) -> dict:
    content = await read_upload_with_limit(file)
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

    import numpy as np

    model, diag = fit_battery_model(
        np.ascontiguousarray(df["flight_time_min"].to_numpy(), dtype=np.float64),
        np.ascontiguousarray(df["payload_kg"].to_numpy(), dtype=np.float64),
        np.ascontiguousarray(df["ground_speed_mps"].to_numpy(), dtype=np.float64),
        np.ascontiguousarray(df["headwind_mps"].to_numpy(), dtype=np.float64),
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
    total = m.predict_total_time_min(req.payload_kg, req.ground_speed_mps, req.headwind_mps)
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
