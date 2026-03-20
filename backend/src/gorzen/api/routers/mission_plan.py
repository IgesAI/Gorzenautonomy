"""Mission planning endpoints: waypoint CRUD, analysis, GeoJSON, drone upload/download."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from gorzen.services.mission_planner import (
    Waypoint,
    analyze_mission,
    mission_service,
    waypoints_to_geojson,
)

router = APIRouter()


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


@router.get("/waypoints")
async def get_waypoints() -> dict[str, Any]:
    """Get current mission waypoints and analysis."""
    wps = mission_service.waypoints
    analysis = mission_service.get_analysis()
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
async def set_mission(mission: MissionInput) -> dict[str, Any]:
    """Set the entire mission plan (replaces existing waypoints)."""
    waypoints = [_wp_from_input(w) for w in mission.waypoints]
    analysis = mission_service.set_waypoints(waypoints)
    return {
        "waypoint_count": len(waypoints),
        "analysis": analysis.__dict__,
    }


@router.post("/waypoints/add")
async def add_waypoint(wp: WaypointInput) -> dict[str, Any]:
    """Add a single waypoint to the end of the mission."""
    analysis = mission_service.add_waypoint(_wp_from_input(wp))
    return {
        "waypoint_count": len(mission_service.waypoints),
        "analysis": analysis.__dict__,
    }


@router.delete("/waypoints/{index}")
async def remove_waypoint(index: int) -> dict[str, Any]:
    """Remove a waypoint by index."""
    analysis = mission_service.remove_waypoint(index)
    return {
        "waypoint_count": len(mission_service.waypoints),
        "analysis": analysis.__dict__,
    }


@router.delete("/waypoints")
async def clear_mission() -> dict[str, str]:
    """Clear all waypoints."""
    mission_service.clear()
    return {"status": "cleared"}


@router.get("/analysis")
async def get_analysis() -> dict[str, Any]:
    """Get mission analysis (distance, duration, etc.)."""
    analysis = mission_service.get_analysis()
    return {"analysis": analysis.__dict__}


@router.get("/geojson")
async def get_geojson() -> dict[str, Any]:
    """Get mission as GeoJSON for map display."""
    return mission_service.get_geojson()


@router.post("/upload")
async def upload_to_drone(req: DroneAddress) -> dict[str, Any]:
    """Upload mission to PX4 drone via MAVSDK."""
    return await mission_service.upload_to_drone(req.address)


@router.post("/download")
async def download_from_drone(req: DroneAddress) -> dict[str, Any]:
    """Download mission from PX4 drone via MAVSDK."""
    return await mission_service.download_from_drone(req.address)
