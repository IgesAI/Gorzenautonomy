"""Persistence helpers for telemetry log metadata."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db.models import TelemetryLogDB


async def list_telemetry_logs(
    session: AsyncSession,
    *,
    twin_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TelemetryLogDB]:
    stmt = select(TelemetryLogDB).order_by(TelemetryLogDB.uploaded_at.desc())
    if twin_id is not None:
        stmt = stmt.where(TelemetryLogDB.twin_id == twin_id)
    stmt = stmt.offset(offset).limit(limit)
    return list((await session.scalars(stmt)).all())


async def get_telemetry_log(session: AsyncSession, log_id: UUID) -> TelemetryLogDB | None:
    return await session.get(TelemetryLogDB, log_id)


async def create_telemetry_log(
    session: AsyncSession,
    *,
    source_format: str,
    file_path: str,
    twin_id: UUID | None = None,
    vehicle_id: str = "",
    firmware_version: str = "",
    file_size_bytes: int = 0,
    record_count: int = 0,
    topics: list | None = None,
    log_metadata: dict | None = None,
) -> TelemetryLogDB:
    row = TelemetryLogDB(
        twin_id=twin_id,
        source_format=source_format,
        vehicle_id=vehicle_id,
        firmware_version=firmware_version,
        file_path=file_path,
        file_size_bytes=file_size_bytes,
        record_count=record_count,
        topics=topics or [],
        log_metadata=log_metadata or {},
    )
    session.add(row)
    await session.flush()
    return row


async def update_telemetry_log(
    session: AsyncSession,
    log_id: UUID,
    **fields: object,
) -> TelemetryLogDB | None:
    row = await session.get(TelemetryLogDB, log_id)
    if row is None:
        return None
    allowed = {
        "twin_id", "source_format", "vehicle_id", "firmware_version",
        "file_path", "file_size_bytes", "record_count", "topics", "log_metadata",
    }
    for key, value in fields.items():
        if key in allowed:
            setattr(row, key, value)
    await session.flush()
    return row


async def delete_telemetry_log(session: AsyncSession, log_id: UUID) -> bool:
    row = await session.get(TelemetryLogDB, log_id)
    if row is None:
        return False
    await session.delete(row)
    return True
