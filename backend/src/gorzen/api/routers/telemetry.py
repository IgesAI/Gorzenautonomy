"""Telemetry & flight data endpoints: MAVLink, PX4 params, flight logs, ROS 2 bridge ingestion."""

from __future__ import annotations

import asyncio
import time
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.api.deps import decode_token
from gorzen.config import settings
from gorzen.db import calibration_repo, telemetry_repo
from gorzen.db.session import get_session
from gorzen.services.flight_log import (
    extract_calibration_data,
    extract_timeseries,
    full_analysis,
    get_available_topics,
    parse_ulog,
)
from gorzen.services.mavlink_telemetry import telemetry_service
from gorzen.services.px4_params import (
    get_param_map,
    get_px4_groups,
    px4_to_twin,
    twin_to_px4,
)

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


async def read_upload_with_limit(file: UploadFile, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"File too large (max {max_bytes // (1024 * 1024)} MB)")
    return data


router = APIRouter()
# WebSocket is registered separately without global HTTP auth (use ?token= when JWT is enabled).
ws_router = APIRouter()
# Internal router for service-to-service calls (ROS 2 bridge → planner), no JWT required.
internal_router = APIRouter()


# --- Connection ---


class ConnectRequest(BaseModel):
    address: str = "udp://:14540"


@router.post("/connect")
async def connect_drone(request: ConnectRequest) -> dict[str, Any]:
    """Connect to a PX4 drone or SITL instance."""
    success = await telemetry_service.connect(request.address)
    hint = telemetry_service.last_connect_hint
    return {
        "connected": success,
        "address": request.address,
        "message": "Connected successfully"
        if success
        else "Connection failed — check address and drone status",
        **({"hint": hint} if not success and hint else {}),
    }


@router.post("/disconnect")
async def disconnect_drone() -> dict[str, str]:
    """Disconnect from the current drone."""
    await telemetry_service.disconnect()
    return {"status": "disconnected"}


@router.get("/status")
async def get_connection_status() -> dict[str, Any]:
    """Get current connection and telemetry status."""
    return {
        "connected": telemetry_service.is_connected,
        "connection": {
            "address": telemetry_service.connection.address,
            "uptime_s": round(telemetry_service.connection.uptime_s, 1),
            "messages_received": telemetry_service.connection.messages_received,
        },
    }


# --- Live Telemetry ---


@router.get("/snapshot")
async def get_telemetry_snapshot() -> dict[str, Any]:
    """Get the latest telemetry frame as a single snapshot."""
    return telemetry_service.get_snapshot()


class BridgeIngestPayload(BaseModel):
    """Telemetry frame POSTed by the gorzen-bridge ROS 2 node."""

    source: str = "ros2_bridge"
    timestamp: float = 0.0
    position: dict[str, float] = {}
    attitude: dict[str, float] = {}
    velocity: dict[str, float] = {}
    battery: dict[str, float] = {}
    gps: dict[str, Any] = {}
    wind: dict[str, float] = {}
    status: dict[str, Any] = {}


@internal_router.post("/ingest")
async def ingest_bridge_telemetry(payload: BridgeIngestPayload) -> dict[str, str]:
    """Accept a telemetry frame from the ROS 2 bridge and inject it into
    the existing telemetry service so the frontend WebSocket sees it.

    This creates a second telemetry path alongside pymavlink, allowing
    A/B comparison from the same frontend.
    """
    frame = telemetry_service.frame
    pos = payload.position
    att = payload.attitude
    vel = payload.velocity
    bat = payload.battery
    gps = payload.gps
    wind = payload.wind
    status = payload.status

    frame.timestamp = payload.timestamp or time.time()
    frame.latitude_deg = pos.get("latitude_deg", frame.latitude_deg)
    frame.longitude_deg = pos.get("longitude_deg", frame.longitude_deg)
    frame.absolute_altitude_m = pos.get("absolute_altitude_m", frame.absolute_altitude_m)
    frame.relative_altitude_m = pos.get("relative_altitude_m", frame.relative_altitude_m)
    frame.roll_deg = att.get("roll_deg", frame.roll_deg)
    frame.pitch_deg = att.get("pitch_deg", frame.pitch_deg)
    frame.yaw_deg = att.get("yaw_deg", frame.yaw_deg)
    frame.groundspeed_ms = vel.get("groundspeed_ms", frame.groundspeed_ms)
    frame.airspeed_ms = vel.get("airspeed_ms", frame.airspeed_ms)
    frame.climb_rate_ms = vel.get("climb_rate_ms", frame.climb_rate_ms)
    frame.velocity_north_ms = vel.get("velocity_north_ms", frame.velocity_north_ms)
    frame.velocity_east_ms = vel.get("velocity_east_ms", frame.velocity_east_ms)
    frame.velocity_down_ms = vel.get("velocity_down_ms", frame.velocity_down_ms)
    frame.battery_voltage_v = bat.get("voltage_v", frame.battery_voltage_v)
    frame.battery_current_a = bat.get("current_a", frame.battery_current_a)
    frame.battery_remaining_pct = bat.get("remaining_pct", frame.battery_remaining_pct)
    frame.gps_fix_type = str(gps.get("fix_type", frame.gps_fix_type))
    frame.gps_num_satellites = int(gps.get("num_satellites", frame.gps_num_satellites))
    frame.wind_speed_ms = wind.get("speed_ms", frame.wind_speed_ms)
    frame.wind_direction_deg = wind.get("direction_deg", frame.wind_direction_deg)
    frame.flight_mode = str(status.get("flight_mode", frame.flight_mode))
    frame.armed = bool(status.get("armed", frame.armed))
    frame.in_air = bool(status.get("in_air", frame.in_air))
    frame.health_ok = bool(status.get("health_ok", frame.health_ok))

    if not telemetry_service.is_connected:
        telemetry_service.connection.connected = True
        telemetry_service.connection.address = f"ros2_bridge:{payload.source}"

    return {"status": "ingested", "source": payload.source}


@ws_router.websocket("/ws")
async def telemetry_websocket(ws: WebSocket) -> None:
    """WebSocket endpoint for live telemetry streaming at ~10 Hz."""
    if settings.auth_enabled:
        token = ws.query_params.get("token")
        if not token:
            await ws.close(code=4401)
            return
        try:
            decode_token(token)
        except HTTPException:
            await ws.close(code=4401)
            return
    await ws.accept()
    q = telemetry_service.subscribe()
    try:
        while True:
            await asyncio.wait_for(q.get(), timeout=5.0)
            await ws.send_json(telemetry_service.get_snapshot())
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        telemetry_service.unsubscribe(q)


# --- PX4 Parameter Mapping ---


@router.get("/params/map")
async def get_parameter_map() -> dict[str, Any]:
    """Get the full twin↔PX4 parameter mapping table."""
    return {
        "mappings": get_param_map(),
        "groups": get_px4_groups(),
        "total": len(get_param_map()),
    }


class TwinParamsRequest(BaseModel):
    params: dict[str, dict[str, Any]]


@router.post("/params/to-px4")
async def convert_twin_to_px4(request: TwinParamsRequest) -> dict[str, Any]:
    """Convert twin parameters to PX4 parameter file format."""
    px4_params = twin_to_px4(request.params)
    return {
        "px4_params": px4_params,
        "count": len(px4_params),
    }


class PX4ParamsRequest(BaseModel):
    params: dict[str, Any]


@router.post("/params/from-px4")
async def convert_px4_to_twin(request: PX4ParamsRequest) -> dict[str, Any]:
    """Convert PX4 parameters back to twin parameter values."""
    twin_params = px4_to_twin(request.params)
    return {
        "twin_params": twin_params,
        "subsystems_affected": list(twin_params.keys()),
    }


# --- Flight Logs ---


@router.post("/logs/upload")
async def upload_flight_log(file: UploadFile) -> dict[str, Any]:
    """Upload and parse a PX4 .ulg flight log file."""
    if not file.filename or not file.filename.endswith(".ulg"):
        raise HTTPException(status_code=400, detail="Only .ulg (PX4 uLog) files are supported")

    data = await read_upload_with_limit(file)
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        summary = parse_ulog(data, filename=file.filename)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse uLog: {e}")

    return {
        "summary": {
            "filename": summary.filename,
            "duration_s": summary.duration_s,
            "topics": summary.topics,
            "parameter_count": len(summary.parameters),
            "message_count": summary.message_count,
            "vehicle_uuid": summary.vehicle_uuid,
            "software_version": summary.software_version,
        },
    }


@router.post("/logs/calibration")
async def extract_calibration(file: UploadFile) -> dict[str, Any]:
    """Upload a uLog and extract calibration data for twin comparison."""
    if not file.filename or not file.filename.endswith(".ulg"):
        raise HTTPException(status_code=400, detail="Only .ulg files supported")

    data = await read_upload_with_limit(file)
    try:
        result = extract_calibration_data(data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to extract calibration data: {e}")

    return result


@router.post("/logs/timeseries")
async def extract_log_timeseries(
    file: UploadFile,
    topic: str = Query(..., description="uLog topic name"),
    field: str = Query(..., description="Field within the topic"),
    downsample: int = Query(500, description="Max data points"),
) -> dict[str, Any]:
    """Extract a specific timeseries from a uLog file."""
    data = await read_upload_with_limit(file)
    try:
        ts = extract_timeseries(data, topic, field, downsample)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Extraction failed: {e}")

    return {
        "topic": ts.topic,
        "field": ts.field,
        "timestamps_s": ts.timestamps_s,
        "values": ts.values,
        "unit": ts.unit,
        "stats": {
            "min": ts.min_val,
            "max": ts.max_val,
            "mean": ts.mean_val,
            "count": len(ts.values),
        },
    }


@router.get("/logs/topics")
async def get_log_topics() -> dict[str, Any]:
    """Get the list of supported calibration topics and fields."""
    return {"topics": get_available_topics()}


@router.post("/logs/analyze")
async def analyze_flight_log(
    file: UploadFile,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Upload, parse, analyze, and persist a PX4 .ulg flight log in one call.

    Returns summary, calibration data, vibration analysis, and flight quality
    scores. Also persists a record to telemetry_logs for future retrieval.
    """
    if not file.filename or not file.filename.endswith(".ulg"):
        raise HTTPException(status_code=400, detail="Only .ulg (PX4 uLog) files are supported")

    data = await read_upload_with_limit(file)
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        result = full_analysis(data, filename=file.filename)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to analyze uLog: {e}")

    summary = result["summary"]
    try:
        log_record = await telemetry_repo.create_telemetry_log(
            session,
            source_format="ulg",
            file_path=summary["filename"],
            vehicle_id=summary.get("vehicle_uuid", ""),
            firmware_version=summary.get("software_version", ""),
            file_size_bytes=len(data),
            record_count=summary.get("message_count", 0),
            topics=summary.get("topics", []),
            log_metadata={
                "duration_s": summary.get("duration_s", 0),
                "parameter_count": summary.get("parameter_count", 0),
                "vibration_pass": result.get("vibration", {}).get("overall_pass"),
            },
        )
        await session.commit()
        result["log_id"] = str(log_record.id)
    except Exception as e:
        result["log_id"] = None
        result["persist_error"] = str(e)

    return result


class CreateCalibrationFromLogRequest(BaseModel):
    log_id: str
    twin_id: str
    mission_type: str = "flight_log_import"


@router.post("/logs/create-calibration")
async def create_calibration_from_log(
    body: CreateCalibrationFromLogRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Create a calibration run record from a previously analyzed flight log.

    Links the log_id to a calibration_run row so PX4 parameters from the log
    can be compared against the digital twin model parameters.
    """
    from uuid import UUID as _UUID
    import hashlib

    try:
        log_uuid = _UUID(body.log_id)
        twin_uuid = _UUID(body.twin_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    log_row = await telemetry_repo.get_telemetry_log(session, log_uuid)
    if log_row is None:
        raise HTTPException(status_code=404, detail="Telemetry log not found")

    config_hash = hashlib.sha256(
        f"{body.twin_id}:{body.log_id}:{body.mission_type}".encode()
    ).hexdigest()[:16]

    posteriors: dict[str, Any] = {}
    if log_row.log_metadata and isinstance(log_row.log_metadata, dict):
        posteriors["source"] = "flight_log"
        posteriors["log_id"] = body.log_id

    run = await calibration_repo.create_calibration_run(
        session,
        twin_id=twin_uuid,
        mission_type=body.mission_type,
        config_hash=config_hash,
        regime="imported",
        posteriors_json=posteriors,
        n_observations=log_row.record_count or 0,
        log_ids=[body.log_id],
    )
    await session.commit()

    return {
        "calibration_run_id": str(run.id),
        "twin_id": body.twin_id,
        "log_id": body.log_id,
        "status": "created",
    }
