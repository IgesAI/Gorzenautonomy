"""Mission execution: MAVSDK upload/download, start, progress."""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gorzen.services.mavlink_mission_coords import (
    normalize_mission_frame_for_raw_upload,
    normalize_xy_to_mavlink_int,
)
from gorzen.services.mavlink_telemetry import telemetry_service
from gorzen.services.mavsdk_connection import get_mavsdk_system
from gorzen.services.preflight import (
    PreflightBlockedError,
    build_preflight_result,
    require_green_light,
)

router = APIRouter()

_ALLOWED_SCHEMES = {"udp", "tcp", "serial"}


def _validate_connection_url(url: str) -> None:
    """Reject URLs with disallowed schemes or private/loopback IP targets."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported scheme '{parsed.scheme}'. Allowed: {', '.join(sorted(_ALLOWED_SCHEMES))}",
        )
    if parsed.hostname:
        try:
            addr = ipaddress.ip_address(parsed.hostname)
            if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
                raise HTTPException(
                    status_code=400,
                    detail="Connection to private/reserved IP addresses is not allowed",
                )
        except ValueError:
            pass


try:
    from mavsdk.mission_raw import MissionItem as RawMissionItem

    HAS_MAVSDK = True
except ImportError:
    HAS_MAVSDK = False


class MissionUploadRequest(BaseModel):
    """Request to upload mission to connected vehicle."""

    connection_url: str = "udp://:14540"  # default: listen for SITL/drone
    mavlink_items: list[dict[str, Any]]
    #: When True (default), the request runs the pre-flight checklist first
    #: and refuses the upload if any red blocking check fails. Operators can
    #: set ``bypass_preflight=True`` for documented dev/test scenarios but
    #: the API logs the bypass.
    bypass_preflight: bool = False


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
    """Convert our MAVLink item dict to MAVSDK MissionRaw.MissionItem.

    ``x``/``y`` may be WGS-84 degrees (planner/export) or already MISSION_ITEM_INT
    scaled integers; see :func:`normalize_xy_to_mavlink_int`.
    """
    xi, yi = normalize_xy_to_mavlink_int(item.get("x", 0), item.get("y", 0))
    frame = normalize_mission_frame_for_raw_upload(item.get("frame"))
    return RawMissionItem(
        seq=seq,
        frame=frame,
        command=int(item.get("command", 16)),
        current=int(item.get("current", 1 if seq == 0 else 0)),
        autocontinue=int(item.get("autocontinue", 1)),
        param1=float(item.get("param1", 0)),
        param2=float(item.get("param2", 0)),
        param3=float(item.get("param3", 0)),
        param4=float(item.get("param4", 0)),
        x=xi,
        y=yi,
        z=float(item.get("z", 0)),
        mission_type=int(item.get("mission_type", 0)),
    )


@router.post("/upload", response_model=MissionUploadResponse)
async def upload_mission(req: MissionUploadRequest) -> MissionUploadResponse:
    """Upload mission to vehicle via MAVSDK (MissionRaw for MAVLink compatibility).

    Runs the pre-flight checklist first; any red blocking check aborts the
    upload with 412 Precondition Failed. Set ``bypass_preflight=true`` to
    override for documented dev/test scenarios.
    """
    if not HAS_MAVSDK:
        raise HTTPException(
            status_code=501,
            detail="MAVSDK not installed. Install with: pip install mavsdk",
        )

    _validate_connection_url(req.connection_url)

    if not req.bypass_preflight:
        # Rudimentary checklist driven by the live telemetry snapshot.
        # Mission-level checks (validation / airspace / risk) should be
        # exercised before this endpoint by the planner UI — we only gate
        # on the FC-side checks here so a direct API caller can't skip
        # the most basic safety interlocks.
        try:
            snap = telemetry_service.get_snapshot()
        except Exception:
            snap = None
        result = build_preflight_result(
            telemetry_snapshot=snap,
            mission_validation=None,
        )
        try:
            require_green_light(result)
        except PreflightBlockedError as exc:
            raise HTTPException(
                status_code=412,
                detail={
                    "status": "preflight_blocked",
                    "blocking_failures": exc.result.blocking_failures,
                    "items": [
                        {
                            "name": i.name,
                            "status": i.status.value,
                            "blocking": i.blocking,
                            "detail": i.detail,
                        }
                        for i in exc.result.items
                    ],
                },
            ) from exc

    try:
        drone = await get_mavsdk_system(req.connection_url)
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e

    raw_items = [_mavlink_to_raw_item(item, seq) for seq, item in enumerate(req.mavlink_items)]
    await drone.mission_raw.upload_mission(raw_items)
    return MissionUploadResponse(
        success=True,
        message="Mission uploaded successfully",
        items_uploaded=len(raw_items),
    )


@router.post("/start")
async def start_mission(connection_url: str = "udp://:14540") -> dict[str, str]:
    """Start the uploaded mission on the connected vehicle."""
    _validate_connection_url(connection_url)

    if not HAS_MAVSDK:
        raise HTTPException(status_code=501, detail="MAVSDK not installed")

    try:
        drone = await get_mavsdk_system(connection_url)
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e

    await drone.mission_raw.start_mission()
    return {"status": "started", "message": "Mission start commanded"}


@router.get("/progress", response_model=MissionProgress)
async def get_mission_progress(connection_url: str = "udp://:14540") -> MissionProgress:
    """Get current mission progress."""
    _validate_connection_url(connection_url)

    if not HAS_MAVSDK:
        raise HTTPException(status_code=501, detail="MAVSDK not installed")

    try:
        drone = await get_mavsdk_system(connection_url)
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e

    progress = await drone.mission_raw.mission_progress()
    return MissionProgress(
        current=progress.current,
        total=progress.total,
        finished=progress.current >= progress.total,
    )
