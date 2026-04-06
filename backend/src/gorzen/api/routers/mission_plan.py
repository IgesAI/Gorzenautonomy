"""Mission planning endpoints: waypoint CRUD, analysis, GeoJSON, drone upload/download."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.api.deps import AuthUserDep
from gorzen.db import audit_repo, mission_repo
from gorzen.db.session import get_session
from gorzen.services.mission_planner import (
    MissionService,
    Waypoint,
    waypoints_from_json,
    waypoints_to_json,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Validation request / response models
# ---------------------------------------------------------------------------


class ValidateRequest(BaseModel):
    """Request body for pre-flight mission validation.

    Perception / overlap fields mirror :func:`gorzen.services.mission_validator.validate_mission`.
    When omitted, checks that require them report INSUFFICIENT_DATA (strict mode).
    """

    twin_id: str
    twin_params: dict[str, Any]
    environment: dict[str, Any] | None = None
    geofence: list[tuple[float, float]] | None = None
    terrain_elevations_m: list[float] | None = None
    required_payload_kg: float | None = None
    target_size_m: float | None = None
    min_pixels_on_target: float | None = None
    max_gsd_cm_px: float | None = None
    exposure_time_s: float | None = None
    max_blur_px: float | None = None
    min_overlap_pct: float | None = None
    trigger_interval_m: float | None = None


class CheckResultResponse(BaseModel):
    name: str
    passed: bool
    value: float
    limit: float
    unit: str
    detail: str


class ValidateResponse(BaseModel):
    is_valid: bool
    checks: list[CheckResultResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WaypointInput(BaseModel):
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    speed_ms: float = 15.0
    loiter_time_s: float = 0.0
    acceptance_radius_m: float = 5.0
    camera_action: str = "none"
    gimbal_pitch_deg: float = -90.0
    yaw_deg: float = float("nan")
    is_fly_through: bool = True


class MissionInput(BaseModel):
    waypoints: list[WaypointInput]


class DroneAddress(BaseModel):
    address: str = "udp://:14540"


def _wp_from_input(inp: WaypointInput) -> Waypoint:
    return Waypoint(
        latitude_deg=inp.latitude_deg,
        longitude_deg=inp.longitude_deg,
        altitude_m=inp.altitude_m,
        speed_ms=inp.speed_ms,
        loiter_time_s=inp.loiter_time_s,
        acceptance_radius_m=inp.acceptance_radius_m,
        camera_action=inp.camera_action,
        gimbal_pitch_deg=inp.gimbal_pitch_deg,
        yaw_deg=inp.yaw_deg,
        is_fly_through=inp.is_fly_through,
    )


async def _load_mission_service(session: AsyncSession, user_sub: str) -> MissionService:
    await mission_repo.ensure_mission_draft_row(session, user_sub)
    raw = await mission_repo.load_waypoints_json(session, user_sub)
    ms = MissionService()
    if raw:
        ms.set_waypoints(waypoints_from_json(raw))
    return ms


async def _persist_waypoints(session: AsyncSession, user_sub: str, ms: MissionService) -> None:
    await mission_repo.save_waypoints_json(session, user_sub, waypoints_to_json(ms.waypoints))


@router.get("/waypoints")
async def get_waypoints(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> dict[str, Any]:
    """Get current mission waypoints and analysis."""
    ms = await _load_mission_service(session, user.username)
    wps = ms.waypoints
    analysis = ms.get_analysis()
    return {
        "waypoints": [
            {
                "order": wp.order,
                "latitude_deg": wp.latitude_deg,
                "longitude_deg": wp.longitude_deg,
                "altitude_m": wp.altitude_m,
                "speed_ms": wp.speed_ms,
                "loiter_time_s": wp.loiter_time_s,
                "camera_action": wp.camera_action,
                "is_fly_through": wp.is_fly_through,
            }
            for wp in wps
        ],
        "analysis": analysis.__dict__,
    }


@router.post("/waypoints")
async def set_mission(
    mission: MissionInput,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> dict[str, Any]:
    """Set the entire mission plan (replaces existing waypoints)."""
    ms = await _load_mission_service(session, user.username)
    waypoints = [_wp_from_input(w) for w in mission.waypoints]
    analysis = ms.set_waypoints(waypoints)
    await _persist_waypoints(session, user.username, ms)
    await audit_repo.record_event(
        session,
        event_type="mission.plan_set",
        actor=user.username,
        payload={"waypoint_count": len(waypoints)},
    )
    return {
        "waypoint_count": len(waypoints),
        "analysis": analysis.__dict__,
    }


@router.post("/waypoints/add")
async def add_waypoint(
    wp: WaypointInput,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> dict[str, Any]:
    """Add a single waypoint to the end of the mission."""
    ms = await _load_mission_service(session, user.username)
    analysis = ms.add_waypoint(_wp_from_input(wp))
    await _persist_waypoints(session, user.username, ms)
    return {
        "waypoint_count": len(ms.waypoints),
        "analysis": analysis.__dict__,
    }


@router.delete("/waypoints/{index}")
async def remove_waypoint(
    index: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> dict[str, Any]:
    """Remove a waypoint by index."""
    ms = await _load_mission_service(session, user.username)
    analysis = ms.remove_waypoint(index)
    await _persist_waypoints(session, user.username, ms)
    return {
        "waypoint_count": len(ms.waypoints),
        "analysis": analysis.__dict__,
    }


@router.delete("/waypoints")
async def clear_mission(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> dict[str, str]:
    """Clear all waypoints."""
    ms = await _load_mission_service(session, user.username)
    ms.clear()
    await _persist_waypoints(session, user.username, ms)
    await audit_repo.record_event(
        session,
        event_type="mission.plan_cleared",
        actor=user.username,
    )
    return {"status": "cleared"}


@router.get("/analysis")
async def get_analysis(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> dict[str, Any]:
    """Get mission analysis (distance, duration, etc.)."""
    ms = await _load_mission_service(session, user.username)
    analysis = ms.get_analysis()
    return {"analysis": analysis.__dict__}


@router.get("/geojson")
async def get_geojson(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> dict[str, Any]:
    """Get mission as GeoJSON for map display."""
    ms = await _load_mission_service(session, user.username)
    return ms.get_geojson()


@router.post("/upload")
async def upload_to_drone(
    req: DroneAddress,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> dict[str, Any]:
    """Upload mission to PX4 drone via MAVSDK."""
    ms = await _load_mission_service(session, user.username)
    return await ms.upload_to_drone(req.address)


@router.post("/download")
async def download_from_drone(
    req: DroneAddress,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> dict[str, Any]:
    """Download mission from PX4 drone via MAVSDK."""
    ms = await _load_mission_service(session, user.username)
    result = await ms.download_from_drone(req.address)
    if result.get("success"):
        await _persist_waypoints(session, user.username, ms)
    return result


@router.post("/import/plan")
async def import_qgc_plan_json(
    plan_data: dict[str, Any],
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> dict[str, Any]:
    """Import a QGroundControl .plan JSON into the current mission.

    Send the parsed .plan file content as the request body.
    Replaces current waypoints with imported ones.
    """
    from gorzen.services.mission_export import import_qgc_plan

    plan = import_qgc_plan(plan_data)

    waypoints = [
        Waypoint(
            latitude_deg=wp.latitude_deg,
            longitude_deg=wp.longitude_deg,
            altitude_m=wp.altitude_m,
            speed_ms=wp.speed_ms or 15.0,
            loiter_time_s=wp.hold_time_s,
            acceptance_radius_m=wp.acceptance_radius_m,
        )
        for wp in plan.waypoints
    ]

    ms = await _load_mission_service(session, user.username)
    analysis = ms.set_waypoints(waypoints)
    await _persist_waypoints(session, user.username, ms)
    await audit_repo.record_event(
        session,
        event_type="mission.plan_imported",
        actor=user.username,
        payload={
            "source": "qgc_plan",
            "waypoint_count": len(waypoints),
            "distance_m": plan.estimated_distance_m,
        },
    )

    return {
        "imported": True,
        "waypoint_count": len(waypoints),
        "estimated_distance_m": round(plan.estimated_distance_m, 1),
        "estimated_duration_s": round(plan.estimated_duration_s, 1),
        "analysis": analysis.__dict__,
    }


@router.get("/export/qgc")
async def export_qgc(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> dict[str, Any]:
    """Export current mission as QGroundControl .plan JSON."""
    from gorzen.services.mission_export import export_qgc_plan
    from gorzen.schemas.mission import MissionPlan, WaypointType
    from gorzen.schemas.mission import Waypoint as SchemaWaypoint

    ms = await _load_mission_service(session, user.username)
    wps = ms.waypoints
    schema_wps = [
        SchemaWaypoint(
            sequence=i,
            wp_type=WaypointType.TAKEOFF
            if i == 0
            else (WaypointType.RETURN_TO_LAUNCH if i == len(wps) - 1 else WaypointType.PHOTO),
            latitude_deg=w.latitude_deg,
            longitude_deg=w.longitude_deg,
            altitude_m=w.altitude_m,
            speed_ms=w.speed_ms,
        )
        for i, w in enumerate(wps)
    ]
    plan = MissionPlan(twin_id="default", waypoints=schema_wps)
    return export_qgc_plan(plan)


@router.get("/export/kml")
async def export_kml(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> Any:
    """Export current mission as KML."""
    from fastapi.responses import Response
    from gorzen.services.mission_export import export_kml as _export_kml
    from gorzen.schemas.mission import MissionPlan, WaypointType
    from gorzen.schemas.mission import Waypoint as SchemaWaypoint

    ms = await _load_mission_service(session, user.username)
    wps = ms.waypoints
    schema_wps = [
        SchemaWaypoint(
            sequence=i,
            wp_type=WaypointType.TAKEOFF
            if i == 0
            else (WaypointType.RETURN_TO_LAUNCH if i == len(wps) - 1 else WaypointType.PHOTO),
            latitude_deg=w.latitude_deg,
            longitude_deg=w.longitude_deg,
            altitude_m=w.altitude_m,
            speed_ms=w.speed_ms,
        )
        for i, w in enumerate(wps)
    ]
    plan = MissionPlan(twin_id="default", waypoints=schema_wps)
    kml_str = _export_kml(plan)
    return Response(content=kml_str, media_type="application/vnd.google-earth.kml+xml")


@router.get("/export/px4")
async def export_px4(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> dict[str, Any]:
    """Export current mission as PX4 MissionRaw items."""
    from gorzen.services.mission_export import export_px4_mission
    from gorzen.schemas.mission import MissionPlan, WaypointType
    from gorzen.schemas.mission import Waypoint as SchemaWaypoint

    ms = await _load_mission_service(session, user.username)
    wps = ms.waypoints
    schema_wps = [
        SchemaWaypoint(
            sequence=i,
            wp_type=WaypointType.TAKEOFF
            if i == 0
            else (WaypointType.RETURN_TO_LAUNCH if i == len(wps) - 1 else WaypointType.PHOTO),
            latitude_deg=w.latitude_deg,
            longitude_deg=w.longitude_deg,
            altitude_m=w.altitude_m,
            speed_ms=w.speed_ms,
        )
        for i, w in enumerate(wps)
    ]
    plan = MissionPlan(twin_id="default", waypoints=schema_wps)
    items = export_px4_mission(plan)
    return {"items": items, "count": len(items)}


@router.post("/validate", response_model=ValidateResponse)
async def validate_mission(
    req: ValidateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: AuthUserDep,
) -> ValidateResponse:
    """Run pre-flight validation checks against the current mission plan."""
    from gorzen.schemas.mission import MissionPlan, WaypointType
    from gorzen.schemas.mission import Waypoint as SchemaWaypoint
    from gorzen.services.mission_planner import analyze_mission
    from gorzen.services.mission_validator import validate_mission as run_validation

    ms = await _load_mission_service(session, user.username)
    wps = ms.waypoints
    if not wps:
        return ValidateResponse(
            is_valid=False,
            checks=[],
            warnings=["No waypoints in current mission plan"],
        )

    schema_wps = [
        SchemaWaypoint(
            sequence=i,
            wp_type=WaypointType.TAKEOFF
            if i == 0
            else (WaypointType.RETURN_TO_LAUNCH if i == len(wps) - 1 else WaypointType.NAVIGATE),
            latitude_deg=w.latitude_deg,
            longitude_deg=w.longitude_deg,
            altitude_m=w.altitude_m,
            speed_ms=w.speed_ms,
        )
        for i, w in enumerate(wps)
    ]

    analysis = analyze_mission(wps)
    plan = MissionPlan(
        twin_id=req.twin_id,
        waypoints=schema_wps,
        estimated_duration_s=analysis.estimated_duration_s,
        estimated_distance_m=analysis.total_distance_m,
    )

    result = run_validation(
        plan,
        req.twin_params,
        environment=req.environment,
        geofence=req.geofence,
        terrain_elevations_m=req.terrain_elevations_m,
        required_payload_kg=req.required_payload_kg,
        target_size_m=req.target_size_m,
        min_pixels_on_target=req.min_pixels_on_target,
        max_gsd_cm_px=req.max_gsd_cm_px,
        exposure_time_s=req.exposure_time_s,
        max_blur_px=req.max_blur_px,
        min_overlap_pct=req.min_overlap_pct,
        trigger_interval_m=req.trigger_interval_m,
    )

    return ValidateResponse(
        is_valid=result.is_valid,
        checks=[
            CheckResultResponse(
                name=c.name,
                passed=c.passed,
                value=c.value,
                limit=c.limit,
                unit=c.unit,
                detail=c.detail,
            )
            for c in result.checks
        ],
        warnings=result.warnings,
    )
