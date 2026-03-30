"""Persistence helpers for the component catalog."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db.models import CatalogEntryDB


async def list_catalog_entries(
    session: AsyncSession,
    subsystem_type: str | None = None,
) -> list[CatalogEntryDB]:
    stmt = select(CatalogEntryDB).order_by(CatalogEntryDB.manufacturer, CatalogEntryDB.model_name)
    if subsystem_type is not None:
        stmt = stmt.where(CatalogEntryDB.subsystem_type == subsystem_type)
    return list((await session.scalars(stmt)).all())


async def get_catalog_entry(session: AsyncSession, entry_id: UUID) -> CatalogEntryDB | None:
    return await session.get(CatalogEntryDB, entry_id)


async def create_catalog_entry(
    session: AsyncSession,
    *,
    subsystem_type: str,
    manufacturer: str,
    model_name: str,
    description: str = "",
    parameters: dict | None = None,
    datasheet_url: str | None = None,
) -> CatalogEntryDB:
    row = CatalogEntryDB(
        subsystem_type=subsystem_type,
        manufacturer=manufacturer,
        model_name=model_name,
        description=description,
        parameters=parameters or {},
        datasheet_url=datasheet_url,
    )
    session.add(row)
    await session.flush()
    return row


async def update_catalog_entry(
    session: AsyncSession,
    entry_id: UUID,
    **fields: object,
) -> CatalogEntryDB | None:
    row = await session.get(CatalogEntryDB, entry_id)
    if row is None:
        return None
    allowed = {
        "subsystem_type",
        "manufacturer",
        "model_name",
        "description",
        "parameters",
        "datasheet_url",
    }
    for key, value in fields.items():
        if key in allowed:
            setattr(row, key, value)
    await session.flush()
    return row


async def delete_catalog_entry(session: AsyncSession, entry_id: UUID) -> bool:
    row = await session.get(CatalogEntryDB, entry_id)
    if row is None:
        return False
    await session.delete(row)
    return True


async def seed_catalog_if_empty(session: AsyncSession) -> int:
    """Insert seed catalog rows when the table is empty. Returns count inserted."""
    from gorzen.schemas.catalog import build_seed_catalog

    count_stmt = select(CatalogEntryDB.id).limit(1)
    existing = (await session.scalars(count_stmt)).first()
    if existing is not None:
        return 0

    seed = build_seed_catalog()
    added = 0
    for entry in seed:
        row = CatalogEntryDB(
            subsystem_type=entry.subsystem_type,
            manufacturer=entry.manufacturer,
            model_name=entry.model_name,
            description=entry.description,
            parameters=entry.parameters,
            datasheet_url=entry.datasheet_url,
        )
        session.add(row)
        added += 1
    await session.flush()
    return added
