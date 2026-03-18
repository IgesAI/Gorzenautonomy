"""Mission planning endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gorzen.api.routers.twin import _twins
from gorzen.schemas.mission import MissionPlanRequest, MissionPlanResponse
from gorzen.solver.mission_planner import plan_mission

router = APIRouter()


@router.post("/{twin_id}/mission", response_model=MissionPlanResponse)
async def create_mission_plan(twin_id: str, request: MissionPlanRequest) -> MissionPlanResponse:
    if twin_id not in _twins:
        raise HTTPException(status_code=404, detail="Twin not found")

    twin = _twins[twin_id]
    request.twin_id = twin_id
    response = plan_mission(twin, request)
    return response
