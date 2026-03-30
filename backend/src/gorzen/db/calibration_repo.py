"""Persistence helpers for calibration runs."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db.models import CalibrationRunDB


async def list_calibration_runs(
    session: AsyncSession,
    *,
    twin_id: UUID | None = None,
    mission_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CalibrationRunDB]:
    stmt = select(CalibrationRunDB).order_by(CalibrationRunDB.created_at.desc())
    if twin_id is not None:
        stmt = stmt.where(CalibrationRunDB.twin_id == twin_id)
    if mission_type is not None:
        stmt = stmt.where(CalibrationRunDB.mission_type == mission_type)
    stmt = stmt.offset(offset).limit(limit)
    return list((await session.scalars(stmt)).all())


async def get_calibration_run(session: AsyncSession, run_id: UUID) -> CalibrationRunDB | None:
    return await session.get(CalibrationRunDB, run_id)


async def create_calibration_run(
    session: AsyncSession,
    *,
    twin_id: UUID,
    mission_type: str,
    config_hash: str,
    regime: str = "",
    posteriors_json: dict | None = None,
    n_observations: int = 0,
    log_marginal_likelihood: float = 0.0,
    log_ids: list | None = None,
) -> CalibrationRunDB:
    row = CalibrationRunDB(
        twin_id=twin_id,
        mission_type=mission_type,
        config_hash=config_hash,
        regime=regime,
        posteriors_json=posteriors_json or {},
        n_observations=n_observations,
        log_marginal_likelihood=log_marginal_likelihood,
        log_ids=log_ids or [],
    )
    session.add(row)
    await session.flush()
    return row


async def delete_calibration_run(session: AsyncSession, run_id: UUID) -> bool:
    row = await session.get(CalibrationRunDB, run_id)
    if row is None:
        return False
    await session.delete(row)
    return True
