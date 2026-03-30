"""Repository functions for prediction_sets and validation_runs."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db.models import PredictionSetDB, ValidationRunDB


async def create_prediction_set(
    session: AsyncSession,
    *,
    mission_id: uuid.UUID,
    twin_id: uuid.UUID,
    predictions: dict[str, Any],
    envelope_hash: str = "",
    model_version: str = "",
) -> PredictionSetDB:
    row = PredictionSetDB(
        mission_id=mission_id,
        twin_id=twin_id,
        predictions=predictions,
        envelope_hash=envelope_hash,
        model_version=model_version,
    )
    session.add(row)
    return row


async def get_prediction_set(session: AsyncSession, prediction_id: uuid.UUID) -> PredictionSetDB | None:
    return await session.get(PredictionSetDB, prediction_id)


async def get_predictions_for_mission(
    session: AsyncSession, mission_id: uuid.UUID
) -> list[PredictionSetDB]:
    stmt = (
        select(PredictionSetDB)
        .where(PredictionSetDB.mission_id == mission_id)
        .order_by(PredictionSetDB.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_validation_run(
    session: AsyncSession,
    *,
    prediction_id: uuid.UUID,
    mission_id: uuid.UUID,
    actuals: dict[str, Any],
    deltas: dict[str, Any],
    source: str = "simulation",
    bag_path: str | None = None,
    confidence_update: dict[str, Any] | None = None,
) -> ValidationRunDB:
    row = ValidationRunDB(
        prediction_id=prediction_id,
        mission_id=mission_id,
        actuals=actuals,
        deltas=deltas,
        source=source,
        bag_path=bag_path,
        confidence_update=confidence_update,
    )
    session.add(row)
    return row


async def get_validation_run(session: AsyncSession, run_id: uuid.UUID) -> ValidationRunDB | None:
    return await session.get(ValidationRunDB, run_id)


async def get_validations_for_mission(
    session: AsyncSession, mission_id: uuid.UUID
) -> list[ValidationRunDB]:
    stmt = (
        select(ValidationRunDB)
        .where(ValidationRunDB.mission_id == mission_id)
        .order_by(ValidationRunDB.completed_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
