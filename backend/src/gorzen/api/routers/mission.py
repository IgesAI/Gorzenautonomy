"""Mission planning endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db import twin_repo
from gorzen.db.session import get_session
from gorzen.schemas.mission import MissionPlanRequest, MissionPlanResponse
from gorzen.solver.mission_planner import plan_mission

router = APIRouter()


@router.post("/{twin_id}/mission", response_model=MissionPlanResponse)
async def create_mission_plan(
    twin_id: str,
    request: MissionPlanRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MissionPlanResponse:
    twin = await twin_repo.get_vehicle_twin(session, twin_id)
    if twin is None:
        raise HTTPException(status_code=404, detail="Twin not found")

    request.twin_id = twin_id
    return plan_mission(twin, request)
