"""Component catalog CRUD endpoints (DB-backed with seed fallback)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db import catalog_repo
from gorzen.db.session import get_session
from gorzen.schemas.catalog import ComponentCatalogEntry, build_seed_catalog

router = APIRouter()

_seed_catalog: list[ComponentCatalogEntry] | None = None


def _get_seed_catalog() -> list[ComponentCatalogEntry]:
    global _seed_catalog
    if _seed_catalog is None:
        _seed_catalog = build_seed_catalog()
    return _seed_catalog


def _row_to_dict(row: object) -> dict[str, Any]:
    return {
        "id": str(row.id),  # type: ignore[attr-defined]
        "subsystem_type": row.subsystem_type,  # type: ignore[attr-defined]
        "manufacturer": row.manufacturer,  # type: ignore[attr-defined]
        "model_name": row.model_name,  # type: ignore[attr-defined]
        "description": row.description,  # type: ignore[attr-defined]
        "parameters": row.parameters,  # type: ignore[attr-defined]
        "datasheet_url": row.datasheet_url,  # type: ignore[attr-defined]
        "created_at": row.created_at.isoformat() if row.created_at else None,  # type: ignore[attr-defined]
    }


class CatalogEntryCreate(BaseModel):
    subsystem_type: str
    manufacturer: str
    model_name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    datasheet_url: str | None = None


class CatalogEntryUpdate(BaseModel):
    subsystem_type: str | None = None
    manufacturer: str | None = None
    model_name: str | None = None
    description: str | None = None
    parameters: dict[str, Any] | None = None
    datasheet_url: str | None = None


@router.get("/", response_model=list[dict[str, Any]])
async def list_catalog(
    session: Annotated[AsyncSession, Depends(get_session)],
    subsystem_type: str | None = None,
) -> list[dict[str, Any]]:
    """List catalog entries from DB; falls back to in-memory seed if DB is empty."""
    rows = await catalog_repo.list_catalog_entries(session, subsystem_type=subsystem_type)
    if rows:
        return [_row_to_dict(r) for r in rows]
    seed = _get_seed_catalog()
    if subsystem_type is not None:
        seed = [e for e in seed if e.subsystem_type == subsystem_type]
    return [e.model_dump(mode="json") for e in seed]


@router.get("/{entry_id}")
async def get_catalog_entry(
    entry_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    row = await catalog_repo.get_catalog_entry(session, entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Catalog entry not found")
    return _row_to_dict(row)


@router.post("/", status_code=201)
async def create_catalog_entry(
    body: CatalogEntryCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    row = await catalog_repo.create_catalog_entry(
        session,
        subsystem_type=body.subsystem_type,
        manufacturer=body.manufacturer,
        model_name=body.model_name,
        description=body.description,
        parameters=body.parameters,
        datasheet_url=body.datasheet_url,
    )
    return _row_to_dict(row)


@router.put("/{entry_id}")
async def update_catalog_entry(
    entry_id: UUID,
    body: CatalogEntryUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    row = await catalog_repo.update_catalog_entry(session, entry_id, **updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Catalog entry not found")
    return _row_to_dict(row)


@router.delete("/{entry_id}")
async def delete_catalog_entry(
    entry_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    ok = await catalog_repo.delete_catalog_entry(session, entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Catalog entry not found")
    return {"status": "deleted"}


@router.post("/seed", status_code=201)
async def seed_catalog(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Populate the catalog table from built-in seed data (no-op if already populated)."""
    count = await catalog_repo.seed_catalog_if_empty(session)
    return {"seeded": count}
