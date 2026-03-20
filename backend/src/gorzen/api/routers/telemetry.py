"""Telemetry & flight data endpoints: MAVLink, PX4 params, flight logs."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from gorzen.services.flight_log import (
    extract_calibration_data,
    extract_timeseries,
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

router = APIRouter()


# --- Connection ---

class ConnectRequest(BaseModel):
    address: str = "udp://:14540"


@router.post("/connect")
async def connect_drone(request: ConnectRequest) -> dict[str, Any]:
    """Connect to a PX4 drone or SITL instance."""
    success = await telemetry_service.connect(request.address)
    return {
        "connected": success,
        "address": request.address,
        "message": "Connected successfully" if success else "Connection failed — check address and drone status",
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


@router.websocket("/ws")
async def telemetry_websocket(ws: WebSocket) -> None:
    """WebSocket endpoint for live telemetry streaming at ~10 Hz."""
    await ws.accept()
    q = telemetry_service.subscribe()
    try:
        while True:
            frame = await asyncio.wait_for(q.get(), timeout=5.0)
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

    data = await file.read()
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

    data = await file.read()
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
    data = await file.read()
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
