"""Persistence helpers for vehicle twins."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db.models import TwinConfigDB
from gorzen.schemas.twin_graph import VehicleTwin


def _vehicle_to_row(twin: VehicleTwin) -> TwinConfigDB:
    v = twin.version
    return TwinConfigDB(
        twin_uuid=twin.twin_id,
        name=twin.name,
        description=twin.description,
        version_major=v.major,
        version_minor=v.minor,
        version_patch=v.patch,
        build_hash=twin.build_hash,
        config_json=twin.model_dump(mode="json"),
        firmware_compat=twin.firmware_compat.model_dump(mode="json"),
        is_active=True,
    )


def _row_to_vehicle(row: TwinConfigDB) -> VehicleTwin:
    return VehicleTwin.model_validate(row.config_json)


async def list_vehicle_twins(session: AsyncSession) -> list[VehicleTwin]:
    stmt = select(TwinConfigDB).where(TwinConfigDB.is_active.is_(True)).order_by(TwinConfigDB.name)
    rows = (await session.scalars(stmt)).all()
    return [_row_to_vehicle(r) for r in rows]


async def get_vehicle_twin(session: AsyncSession, twin_id: str) -> VehicleTwin | None:
    try:
        uid = UUID(twin_id)
    except ValueError:
        return None
    row = await session.get(TwinConfigDB, uid)
    if row is None or not row.is_active:
        return None
    return _row_to_vehicle(row)


async def upsert_vehicle_twin(session: AsyncSession, twin: VehicleTwin) -> VehicleTwin:
    twin = twin.with_hash()
    existing = await session.get(TwinConfigDB, twin.twin_id)
    payload = _vehicle_to_row(twin)
    if existing:
        existing.name = payload.name
        existing.description = payload.description
        existing.version_major = payload.version_major
        existing.version_minor = payload.version_minor
        existing.version_patch = payload.version_patch
        existing.build_hash = payload.build_hash
        existing.config_json = payload.config_json
        existing.firmware_compat = payload.firmware_compat
        existing.is_active = True
        await session.flush()
        return _row_to_vehicle(existing)
    session.add(payload)
    await session.flush()
    return _row_to_vehicle(payload)


async def delete_vehicle_twin(session: AsyncSession, twin_id: str) -> bool:
    try:
        uid = UUID(twin_id)
    except ValueError:
        return False
    row = await session.get(TwinConfigDB, uid)
    if row is None or not row.is_active:
        return False
    row.is_active = False
    return True
