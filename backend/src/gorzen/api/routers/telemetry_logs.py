"""Telemetry log metadata CRUD endpoints."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db import telemetry_repo
from gorzen.db.session import get_session

router = APIRouter()


def _log_to_dict(row: object) -> dict[str, Any]:
    return {
        "id": str(row.id),  # type: ignore[attr-defined]
        "twin_id": str(row.twin_id) if row.twin_id else None,  # type: ignore[attr-defined]
        "source_format": row.source_format,  # type: ignore[attr-defined]
        "vehicle_id": row.vehicle_id,  # type: ignore[attr-defined]
        "firmware_version": row.firmware_version,  # type: ignore[attr-defined]
        "file_path": row.file_path,  # type: ignore[attr-defined]
        "file_size_bytes": row.file_size_bytes,  # type: ignore[attr-defined]
        "record_count": row.record_count,  # type: ignore[attr-defined]
        "topics": row.topics,  # type: ignore[attr-defined]
        "log_metadata": row.log_metadata,  # type: ignore[attr-defined]
        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,  # type: ignore[attr-defined]
    }


class TelemetryLogCreate(BaseModel):
    source_format: str
    file_path: str
    twin_id: UUID | None = None
    vehicle_id: str = ""
    firmware_version: str = ""
    file_size_bytes: int = 0
    record_count: int = 0
    topics: list[str] = Field(default_factory=list)
    log_metadata: dict[str, Any] = Field(default_factory=dict)


class TelemetryLogUpdate(BaseModel):
    twin_id: UUID | None = None
    source_format: str | None = None
    vehicle_id: str | None = None
    firmware_version: str | None = None
    file_path: str | None = None
    file_size_bytes: int | None = None
    record_count: int | None = None
    topics: list[str] | None = None
    log_metadata: dict[str, Any] | None = None


@router.get("/", response_model=list[dict[str, Any]])
async def list_logs(
    session: Annotated[AsyncSession, Depends(get_session)],
    twin_id: str | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    uid: UUID | None = None
    if twin_id is not None:
        try:
            uid = UUID(twin_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid twin_id") from None
    rows = await telemetry_repo.list_telemetry_logs(session, twin_id=uid, limit=limit, offset=offset)
    return [_log_to_dict(r) for r in rows]


@router.get("/{log_id}")
async def get_log(
    log_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    row = await telemetry_repo.get_telemetry_log(session, log_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Telemetry log not found")
    return _log_to_dict(row)


@router.post("/", status_code=201)
async def create_log(
    body: TelemetryLogCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    row = await telemetry_repo.create_telemetry_log(
        session,
        source_format=body.source_format,
        file_path=body.file_path,
        twin_id=body.twin_id,
        vehicle_id=body.vehicle_id,
        firmware_version=body.firmware_version,
        file_size_bytes=body.file_size_bytes,
        record_count=body.record_count,
        topics=body.topics,
        log_metadata=body.log_metadata,
    )
    return _log_to_dict(row)


@router.put("/{log_id}")
async def update_log(
    log_id: UUID,
    body: TelemetryLogUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    row = await telemetry_repo.update_telemetry_log(session, log_id, **updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Telemetry log not found")
    return _log_to_dict(row)


@router.delete("/{log_id}")
async def delete_log(
    log_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    ok = await telemetry_repo.delete_telemetry_log(session, log_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Telemetry log not found")
    return {"status": "deleted"}
