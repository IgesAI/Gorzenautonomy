"""Persistence helpers for the append-only audit trail."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db.models import AuditEventDB


async def record_event(
    session: AsyncSession,
    *,
    event_type: str,
    actor: str = "system",
    twin_id: UUID | None = None,
    payload: dict | None = None,
) -> AuditEventDB:
    row = AuditEventDB(
        event_type=event_type,
        actor=actor,
        twin_id=twin_id,
        payload=payload or {},
    )
    session.add(row)
    await session.flush()
    return row


async def list_events(
    session: AsyncSession,
    *,
    event_type: str | None = None,
    twin_id: UUID | None = None,
    since: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEventDB]:
    stmt = select(AuditEventDB).order_by(AuditEventDB.timestamp.desc())
    if event_type is not None:
        stmt = stmt.where(AuditEventDB.event_type == event_type)
    if twin_id is not None:
        stmt = stmt.where(AuditEventDB.twin_id == twin_id)
    if since is not None:
        stmt = stmt.where(AuditEventDB.timestamp >= since)
    stmt = stmt.offset(offset).limit(limit)
    return list((await session.scalars(stmt)).all())


async def get_event(session: AsyncSession, event_id: UUID) -> AuditEventDB | None:
    return await session.get(AuditEventDB, event_id)
