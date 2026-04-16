"""Persistence helpers for vehicle twins.

Twins are scoped by ``owner_sub`` (JWT ``sub`` of the creator). Callers pass
``owner_sub`` so a user cannot read or mutate another user's twin. When the
caller has the ``admin`` role, router code passes ``owner_sub=None`` to
bypass the filter for support/ops workflows.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db.models import TwinConfigDB
from gorzen.schemas.twin_graph import VehicleTwin


def _vehicle_to_row(twin: VehicleTwin, owner_sub: str) -> TwinConfigDB:
    v = twin.version
    return TwinConfigDB(
        twin_uuid=twin.twin_id,
        owner_sub=owner_sub,
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


async def list_vehicle_twins(
    session: AsyncSession, owner_sub: str | None = None
) -> list[VehicleTwin]:
    stmt = select(TwinConfigDB).where(TwinConfigDB.is_active.is_(True)).order_by(TwinConfigDB.name)
    if owner_sub is not None:
        stmt = stmt.where(TwinConfigDB.owner_sub == owner_sub)
    rows = (await session.scalars(stmt)).all()
    return [_row_to_vehicle(r) for r in rows]


async def get_vehicle_twin(
    session: AsyncSession, twin_id: str, owner_sub: str | None = None
) -> VehicleTwin | None:
    try:
        uid = UUID(twin_id)
    except ValueError:
        return None
    row = await session.get(TwinConfigDB, uid)
    if row is None or not row.is_active:
        return None
    if owner_sub is not None and row.owner_sub != owner_sub:
        return None
    return _row_to_vehicle(row)


async def upsert_vehicle_twin(
    session: AsyncSession, twin: VehicleTwin, owner_sub: str
) -> VehicleTwin:
    twin = twin.with_hash()
    existing = await session.get(TwinConfigDB, twin.twin_id)
    payload = _vehicle_to_row(twin, owner_sub)
    if existing:
        # Guard against ownership hijacking — a non-admin must own the row
        # they're updating. Admin callers pass their own username as owner_sub;
        # they can still overwrite anyone's twin if routed through admin tools
        # that intentionally skip the ownership check before calling us.
        if existing.owner_sub != owner_sub:
            raise PermissionError(
                f"Twin {twin.twin_id} is owned by another user (owner_sub mismatch)"
            )
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


async def delete_vehicle_twin(
    session: AsyncSession, twin_id: str, owner_sub: str | None = None
) -> bool:
    try:
        uid = UUID(twin_id)
    except ValueError:
        return False
    row = await session.get(TwinConfigDB, uid)
    if row is None or not row.is_active:
        return False
    if owner_sub is not None and row.owner_sub != owner_sub:
        return False
    row.is_active = False
    return True
