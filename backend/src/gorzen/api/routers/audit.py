"""Audit trail read-only endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db import audit_repo
from gorzen.db.session import get_session

router = APIRouter()


def _event_to_dict(row: object) -> dict[str, Any]:
    return {
        "id": str(row.id),  # type: ignore[attr-defined]
        "twin_id": str(row.twin_id) if row.twin_id else None,  # type: ignore[attr-defined]
        "event_type": row.event_type,  # type: ignore[attr-defined]
        "actor": row.actor,  # type: ignore[attr-defined]
        "payload": row.payload,  # type: ignore[attr-defined]
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,  # type: ignore[attr-defined]
    }


@router.get("/", response_model=list[dict[str, Any]])
async def list_events(
    session: Annotated[AsyncSession, Depends(get_session)],
    event_type: str | None = None,
    twin_id: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    uid: UUID | None = None
    if twin_id is not None:
        try:
            uid = UUID(twin_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid twin_id") from None
    rows = await audit_repo.list_events(
        session,
        event_type=event_type,
        twin_id=uid,
        since=since,
        limit=limit,
        offset=offset,
    )
    return [_event_to_dict(r) for r in rows]


@router.get("/{event_id}")
async def get_event(
    event_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    row = await audit_repo.get_event(session, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return _event_to_dict(row)
