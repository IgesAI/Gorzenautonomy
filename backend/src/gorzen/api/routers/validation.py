"""Post-flight validation: PyODM orthophoto/DEM generation."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

try:
    from gorzen.validation.pyodm_client import HAS_PYODM, run_odm_task
except ImportError:
    HAS_PYODM = False
    run_odm_task = None


class ODMTaskRequest(BaseModel):
    host: str = "localhost"
    port: int = 3000
    images: list[str]
    options: dict | None = None


@router.post("/odm/task")
async def create_odm_task(req: ODMTaskRequest) -> dict:
    """Create ODM task for post-flight orthophoto/DEM validation.

    Requires NodeODM running (e.g. docker run -p 3000:3000 opendronemap/nodeodm).
    Install with: pip install gorzen[odm]
    """
    if not HAS_PYODM or run_odm_task is None:
        raise HTTPException(
            status_code=501,
            detail="PyODM not installed. Install with: pip install gorzen[odm]",
        )
    return await asyncio.to_thread(
        run_odm_task,
        host=req.host,
        port=req.port,
        images=req.images,
        options=req.options,
    )
