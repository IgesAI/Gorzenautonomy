"""Mission execution: MAVSDK upload/download, start, progress."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

try:
    from mavsdk import System
    from mavsdk.mission_raw import MissionItem as RawMissionItem
    HAS_MAVSDK = True
except ImportError:
    HAS_MAVSDK = False


class MissionUploadRequest(BaseModel):
    """Request to upload mission to connected vehicle."""

    connection_url: str = "udp://:14540"  # default: listen for SITL/drone
    mavlink_items: list[dict[str, Any]]


class MissionUploadResponse(BaseModel):
    """Response from mission upload."""

    success: bool
    message: str
    items_uploaded: int = 0


class MissionProgress(BaseModel):
    """Current mission progress."""

    current: int
    total: int
    finished: bool


def _mavlink_to_raw_item(item: dict[str, Any], seq: int) -> "RawMissionItem":
    """Convert our MAVLink item dict to MAVSDK MissionRaw.MissionItem."""
    return RawMissionItem(
        seq=seq,
        frame=int(item.get("frame", 3)),
        command=int(item.get("command", 16)),
        current=int(item.get("current", 1 if seq == 0 else 0)),
        autocontinue=int(item.get("autocontinue", 1)),
        param1=float(item.get("param1", 0)),
        param2=float(item.get("param2", 0)),
        param3=float(item.get("param3", 0)),
        param4=float(item.get("param4", 0)),
        x=int(float(item.get("x", 0)) * 1e7),
        y=int(float(item.get("y", 0)) * 1e7),
        z=float(item.get("z", 0)),
        mission_type=0,
    )


@router.post("/upload", response_model=MissionUploadResponse)
async def upload_mission(req: MissionUploadRequest) -> MissionUploadResponse:
    """Upload mission to vehicle via MAVSDK (MissionRaw for MAVLink compatibility)."""
    if not HAS_MAVSDK:
        raise HTTPException(
            status_code=501,
            detail="MAVSDK not installed. Install with: pip install mavsdk",
        )

    drone = System()
    await drone.connect(system_address=req.connection_url)

    raw_items = [
        _mavlink_to_raw_item(item, seq)
        for seq, item in enumerate(req.mavlink_items)
    ]
    await drone.mission_raw.upload_mission(raw_items)
    return MissionUploadResponse(
        success=True,
        message="Mission uploaded successfully",
        items_uploaded=len(raw_items),
    )


@router.post("/start")
async def start_mission(connection_url: str = "udp://:14540") -> dict[str, str]:
    """Start the uploaded mission on the connected vehicle."""
    if not HAS_MAVSDK:
        raise HTTPException(status_code=501, detail="MAVSDK not installed")

    drone = System()
    await drone.connect(system_address=connection_url)
    await drone.mission_raw.start_mission()
    return {"status": "started", "message": "Mission start commanded"}


@router.get("/progress", response_model=MissionProgress)
async def get_mission_progress(connection_url: str = "udp://:14540") -> MissionProgress:
    """Get current mission progress."""
    if not HAS_MAVSDK:
        raise HTTPException(status_code=501, detail="MAVSDK not installed")

    drone = System()
    await drone.connect(system_address=connection_url)
    progress = await drone.mission_raw.mission_progress()
    return MissionProgress(
        current=progress.current,
        total=progress.total,
        finished=progress.current >= progress.total,
    )
