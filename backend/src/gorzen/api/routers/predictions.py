"""Prediction & validation endpoints for the v2 feedback loop.

- POST /predictions/{mission_id}   — store pre-flight predicted outcomes
- GET  /predictions/{mission_id}   — retrieve predictions for validator
- POST /validations/{mission_id}   — ingest post-flight validation report
- GET  /validations/{mission_id}   — retrieve validation comparison
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db import prediction_repo
from gorzen.db.session import get_session

router = APIRouter()


class CreatePredictionRequest(BaseModel):
    twin_id: str
    predictions: dict[str, Any]
    envelope_hash: str = ""
    model_version: str = ""


class PredictionResponse(BaseModel):
    id: str
    mission_id: str
    twin_id: str
    predictions: dict[str, Any]
    envelope_hash: str
    model_version: str
    created_at: str


class CreateValidationRequest(BaseModel):
    prediction_id: str
    actuals: dict[str, Any]
    deltas: dict[str, Any]
    source: str = "simulation"
    bag_path: str | None = None
    confidence_update: dict[str, Any] | None = None


class ValidationResponse(BaseModel):
    id: str
    prediction_id: str
    mission_id: str
    actuals: dict[str, Any]
    deltas: dict[str, Any]
    source: str
    bag_path: str | None
    confidence_update: dict[str, Any] | None
    completed_at: str


def _prediction_to_response(row: Any) -> PredictionResponse:
    return PredictionResponse(
        id=str(row.id),
        mission_id=str(row.mission_id),
        twin_id=str(row.twin_id),
        predictions=row.predictions,
        envelope_hash=row.envelope_hash,
        model_version=row.model_version,
        created_at=row.created_at.isoformat(),
    )


def _validation_to_response(row: Any) -> ValidationResponse:
    return ValidationResponse(
        id=str(row.id),
        prediction_id=str(row.prediction_id),
        mission_id=str(row.mission_id),
        actuals=row.actuals,
        deltas=row.deltas,
        source=row.source,
        bag_path=row.bag_path,
        confidence_update=row.confidence_update,
        completed_at=row.completed_at.isoformat(),
    )


@router.post("/{mission_id}", response_model=PredictionResponse, status_code=201)
async def create_prediction(
    mission_id: str,
    body: CreatePredictionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PredictionResponse:
    """Store pre-flight predicted outcomes for a mission."""
    try:
        m_uuid = UUID(mission_id)
        t_uuid = UUID(body.twin_id)
    except ValueError:
        raise HTTPException(400, "Invalid UUID format")

    row = await prediction_repo.create_prediction_set(
        session,
        mission_id=m_uuid,
        twin_id=t_uuid,
        predictions=body.predictions,
        envelope_hash=body.envelope_hash,
        model_version=body.model_version,
    )
    await session.commit()
    await session.refresh(row)
    return _prediction_to_response(row)


@router.get("/{mission_id}", response_model=list[PredictionResponse])
async def get_predictions(
    mission_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PredictionResponse]:
    """Retrieve all prediction sets for a mission (newest first)."""
    try:
        m_uuid = UUID(mission_id)
    except ValueError:
        raise HTTPException(400, "Invalid UUID format")

    rows = await prediction_repo.get_predictions_for_mission(session, m_uuid)
    return [_prediction_to_response(r) for r in rows]


# ── Validation endpoints ─────────────────────────────────────────────

validations_router = APIRouter()


@validations_router.post("/{mission_id}", response_model=ValidationResponse, status_code=201)
async def create_validation(
    mission_id: str,
    body: CreateValidationRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ValidationResponse:
    """Ingest a post-flight validation report comparing predicted vs actual."""
    try:
        m_uuid = UUID(mission_id)
        p_uuid = UUID(body.prediction_id)
    except ValueError:
        raise HTTPException(400, "Invalid UUID format")

    pred = await prediction_repo.get_prediction_set(session, p_uuid)
    if pred is None:
        raise HTTPException(404, f"Prediction set {body.prediction_id} not found")

    row = await prediction_repo.create_validation_run(
        session,
        prediction_id=p_uuid,
        mission_id=m_uuid,
        actuals=body.actuals,
        deltas=body.deltas,
        source=body.source,
        bag_path=body.bag_path,
        confidence_update=body.confidence_update,
    )
    await session.commit()
    await session.refresh(row)
    return _validation_to_response(row)


@validations_router.get("/{mission_id}", response_model=list[ValidationResponse])
async def get_validations(
    mission_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ValidationResponse]:
    """Retrieve all validation runs for a mission (newest first)."""
    try:
        m_uuid = UUID(mission_id)
    except ValueError:
        raise HTTPException(400, "Invalid UUID format")

    rows = await prediction_repo.get_validations_for_mission(session, m_uuid)
    return [_validation_to_response(r) for r in rows]
