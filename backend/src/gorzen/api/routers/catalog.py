"""Component catalog browsing endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from gorzen.schemas.catalog import ComponentCatalogEntry, build_seed_catalog

router = APIRouter()

_catalog = build_seed_catalog()


@router.get("/", response_model=list[ComponentCatalogEntry])
async def list_catalog() -> list[ComponentCatalogEntry]:
    return _catalog


@router.get("/{subsystem_type}", response_model=list[ComponentCatalogEntry])
async def list_catalog_by_type(subsystem_type: str) -> list[ComponentCatalogEntry]:
    return [e for e in _catalog if e.subsystem_type == subsystem_type]
