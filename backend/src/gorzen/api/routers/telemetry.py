"""Telemetry & flight data endpoints: MAVLink, PX4 params, flight logs, ROS 2 bridge ingestion."""

from __future__ import annotations

import asyncio
import hmac
import time
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.api.deps import AuthUserDep, decode_token
from gorzen.api.observability import metrics
from gorzen.config import settings
from gorzen.db import calibration_repo, parameter_audit_repo, telemetry_repo
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


def _verify_bridge_token(
    authorization: str | None = Header(default=None),
    x_bridge_token: str | None = Header(default=None, alias="X-Bridge-Token"),
) -> None:
    """Authenticate a ROS 2 bridge (or other service) POSTing telemetry.

    A bridge must present a token in either ``Authorization: Bearer <token>``
    or ``X-Bridge-Token: <token>``. The expected token is configured via
    ``GORZEN_BRIDGE_TOKEN`` and defaults to empty — an empty configured token
    disables this route (returns 503) so a misconfigured server cannot silently
    accept anonymous telemetry.
    """
    expected = settings.bridge_token.strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "Bridge ingest disabled: set GORZEN_BRIDGE_TOKEN to a shared"
                " secret to enable ROS 2 bridge telemetry injection."
            ),
        )

    presented: str | None = x_bridge_token
    if authorization and authorization.lower().startswith("bearer "):
        presented = authorization.split(" ", 1)[1].strip()
    if not presented:
        raise HTTPException(status_code=401, detail="Bridge token required")
    if not hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid bridge token")

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
    link_profile: Literal["default", "low_bandwidth"] = "default"


@router.post("/connect")
async def connect_drone(request: ConnectRequest) -> dict[str, Any]:
    """Connect to a PX4/ArduPilot link. Use ``low_bandwidth`` for LoRa or other low-rate telemetry."""
    success = await telemetry_service.connect(request.address, request.link_profile)
    hint = telemetry_service.last_connect_hint
    return {
        "connected": success,
        "address": request.address,
        "link_profile": request.link_profile,
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
    snap = telemetry_service.get_snapshot()
    return {
        "connected": telemetry_service.is_connected,
        "connection": snap["connection"],
    }


@router.get("/health")
async def get_fc_health() -> dict[str, Any]:
    """Per-sensor health decoded from ``SYS_STATUS``.

    Returns the full 32-bit ``onboard_control_sensors_*`` bitmasks as named
    flags so the pre-flight checklist can pinpoint which sensor failed
    (gyro, diff_pressure, prearm_check, etc.).
    """
    snap = telemetry_service.get_snapshot()
    return {
        "connected": telemetry_service.is_connected,
        "health_ok": snap["status"]["health_ok"],
        "sensor_present": snap["health"]["sensor_present"],
        "sensor_enabled": snap["health"]["sensor_enabled"],
        "sensor_health": snap["health"]["sensor_health"],
        "pre_arm_messages": snap["pre_arm_messages"],
    }


def _record_preflight_metric(ready: bool) -> None:
    metrics.preflight_results_total.inc(status="green" if ready else "red")


@router.get("/preflight")
async def get_preflight_summary() -> dict[str, Any]:
    """Aggregated pre-flight readiness check suitable for gating /execution/upload.

    Returns a ``ready`` boolean plus per-check reasons. A missing required
    telemetry field (e.g. no GPS fix yet) is reported as ``blocking``;
    downstream callers can decide whether to hard-block or warn.
    """
    snap = telemetry_service.get_snapshot()
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, blocking: bool = True) -> None:
        checks.append({"name": name, "passed": ok, "blocking": blocking, "detail": detail})

    add(
        "link_connected",
        snap["connection"]["connected"],
        f"Heartbeat age {snap['connection']['heartbeat_age_s']:.1f}s",
    )
    add(
        "autopilot_identified",
        snap["connection"]["autopilot"] in ("px4", "ardupilot"),
        f"autopilot={snap['connection']['autopilot']}",
    )
    gps_fix = snap["gps"]["fix_type"]
    add(
        "gps_fix_3d_or_better",
        gps_fix in ("3D_FIX", "DGPS", "RTK_FLOAT", "RTK_FIXED"),
        f"fix={gps_fix}, sats={snap['gps']['num_satellites']}",
    )
    add(
        "sensors_healthy",
        snap["status"]["health_ok"] is True,
        f"health_ok={snap['status']['health_ok']}",
    )
    battery_pct = snap["battery"]["remaining_pct"]
    add(
        "battery_above_reserve",
        isinstance(battery_pct, (int, float)) and battery_pct >= 30.0,
        f"battery={battery_pct}%",
    )
    vtol_state = snap["status"]["vtol_state"]
    add(
        "vtol_state_known",
        vtol_state in ("MC", "FW", "TRANSITION_TO_FW", "TRANSITION_TO_MC"),
        f"vtol_state={vtol_state}",
        blocking=False,
    )
    add(
        "no_recent_prearm_errors",
        not any("PREARM" in msg.upper() or "ARM" in msg.upper() for msg in snap["pre_arm_messages"][:4]),
        f"latest={snap['pre_arm_messages'][:2]}",
        blocking=False,
    )

    blocking_failures = [c for c in checks if c["blocking"] and not c["passed"]]
    ready = not blocking_failures
    _record_preflight_metric(ready)
    metrics.telemetry_link_connected.set(1 if snap["connection"]["connected"] else 0)
    return {
        "ready": ready,
        "checks": checks,
        "blocking_failures": [c["name"] for c in blocking_failures],
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


@internal_router.post("/ingest", dependencies=[Depends(_verify_bridge_token)])
async def ingest_bridge_telemetry(payload: BridgeIngestPayload) -> dict[str, str]:
    """Accept a telemetry frame from the ROS 2 bridge and inject it into
    the existing telemetry service so the frontend WebSocket sees it.

    Authenticated via a bridge token (``Authorization: Bearer`` or
    ``X-Bridge-Token`` header). The bridge sets ``GORZEN_BRIDGE_TOKEN`` on
    both sides; without it, anyone on the network could inject telemetry.
    """
    pos = payload.position
    att = payload.attitude
    vel = payload.velocity
    bat = payload.battery
    gps = payload.gps
    wind = payload.wind
    status = payload.status

    # Mutate the frame under the service's own lock so concurrent WebSocket /
    # HTTP readers never see a torn update.
    with telemetry_service._frame_lock:  # noqa: SLF001 — intentional cross-module mutation
        frame = telemetry_service.frame
        frame.timestamp = payload.timestamp or time.time()
        if "latitude_deg" in pos:
            frame.latitude_deg = pos["latitude_deg"]
        if "longitude_deg" in pos:
            frame.longitude_deg = pos["longitude_deg"]
        if "absolute_altitude_m" in pos:
            frame.absolute_altitude_m = pos["absolute_altitude_m"]
        if "relative_altitude_m" in pos:
            frame.relative_altitude_m = pos["relative_altitude_m"]
        if "roll_deg" in att:
            frame.roll_deg = att["roll_deg"]
        if "pitch_deg" in att:
            frame.pitch_deg = att["pitch_deg"]
        if "yaw_deg" in att:
            frame.yaw_deg = att["yaw_deg"]
        if "groundspeed_ms" in vel:
            frame.groundspeed_ms = vel["groundspeed_ms"]
        if "airspeed_ms" in vel:
            frame.airspeed_ms = vel["airspeed_ms"]
        if "climb_rate_ms" in vel:
            frame.climb_rate_ms = vel["climb_rate_ms"]
        if "velocity_north_ms" in vel:
            frame.velocity_north_ms = vel["velocity_north_ms"]
        if "velocity_east_ms" in vel:
            frame.velocity_east_ms = vel["velocity_east_ms"]
        if "velocity_down_ms" in vel:
            frame.velocity_down_ms = vel["velocity_down_ms"]
        if "voltage_v" in bat:
            frame.battery_voltage_v = bat["voltage_v"]
        if "current_a" in bat:
            frame.battery_current_a = bat["current_a"]
        if "remaining_pct" in bat:
            frame.battery_remaining_pct = bat["remaining_pct"]
        if "fix_type" in gps:
            frame.gps_fix_type = str(gps["fix_type"])
        if "num_satellites" in gps:
            frame.gps_num_satellites = int(gps["num_satellites"])
        if "speed_ms" in wind:
            frame.wind_speed_ms = wind["speed_ms"]
        if "direction_deg" in wind:
            frame.wind_direction_deg = wind["direction_deg"]
        if "flight_mode" in status:
            frame.flight_mode = str(status["flight_mode"])
        if "armed" in status:
            frame.armed = bool(status["armed"])
        if "in_air" in status:
            frame.in_air = bool(status["in_air"])
        if "health_ok" in status:
            frame.health_ok = bool(status["health_ok"])

        if not telemetry_service.is_connected:
            telemetry_service.connection.connected = True
            telemetry_service.connection.address = f"ros2_bridge:{payload.source}"
            telemetry_service.connection.last_heartbeat = time.time()
            telemetry_service.connection.autopilot_name = "ros2_bridge"

    return {"status": "ingested", "source": payload.source}


@ws_router.websocket("/ws")
async def telemetry_websocket(ws: WebSocket) -> None:
    """QGC-style WebSocket: polls get_snapshot() directly at 20 Hz.

    Always requires a token (either a JWT when ``auth_enabled`` or the dev
    token ``GORZEN_DEV_TOKEN`` when running unauthenticated). This prevents
    anyone on the network from silently tapping live flight telemetry even
    when running in dev mode.
    """
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4401)
        return
    if settings.auth_enabled:
        try:
            decode_token(token)
        except HTTPException:
            await ws.close(code=4401)
            return
    else:
        expected = settings.dev_ws_token.strip()
        if not expected or not hmac.compare_digest(
            token.encode("utf-8"), expected.encode("utf-8")
        ):
            await ws.close(code=4401)
            return
    await ws.accept()
    last_count = -1
    try:
        while True:
            snap = telemetry_service.get_snapshot()
            count = snap["connection"]["messages_received"]
            if count != last_count:
                await ws.send_json(snap)
                last_count = count
            else:
                await ws.send_json(snap)
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass


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


# --- FC Parameter Sync (QGC-style write-back) ---


class SyncToFCRequest(BaseModel):
    params: dict[str, dict[str, Any]]


@router.post("/params/sync-to-fc")
async def sync_params_to_fc(
    request: SyncToFCRequest,
    user: AuthUserDep,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Write twin parameters to the flight controller.

    Each write is recorded in the ``parameter_audit`` table so operators
    can always trace who pushed what value (old → new) and when.
    """
    if not telemetry_service.is_connected:
        raise HTTPException(400, "No active telemetry connection")

    typed_params = twin_to_px4(request.params)
    if not typed_params:
        return {"synced": 0, "failed": 0, "params": {}}

    loop = asyncio.get_running_loop()
    results: dict[str, bool] = {}
    for name, (value, mav_type) in typed_params.items():
        # Read the old value first so the audit log records the delta.
        probe = await loop.run_in_executor(
            None, lambda n=name: telemetry_service.read_param(n)
        )
        old_value = probe[0] if probe is not None else None
        ok = await loop.run_in_executor(
            None,
            lambda n=name, v=value, t=mav_type: telemetry_service.write_param(n, v, t),
        )
        results[name] = ok
        metrics.param_writes_total.inc(outcome="success" if ok else "failure")
        try:
            await parameter_audit_repo.record_param_write(
                session,
                twin_id=None,
                actor=user.username,
                param_id=name,
                old_value=old_value,
                new_value=value,
                param_type=int(mav_type),
                success=bool(ok),
                context={"source": "sync-to-fc"},
            )
        except Exception as exc:
            # Audit failures must not mask the real operation's result.
            # Log loudly so operators see persistence regressions.
            import structlog

            structlog.get_logger("gorzen.audit").error(
                "param_audit_persist_failed", error=str(exc), param_id=name
            )

    synced = sum(1 for v in results.values() if v)
    return {
        "synced": synced,
        "failed": len(results) - synced,
        "params": results,
    }


@router.post("/params/read-from-fc")
async def read_params_from_fc() -> dict[str, Any]:
    """Read all parameters from the FC and return as twin params.

    Requires an active telemetry connection. Preserves each parameter's true
    ``MAV_PARAM_TYPE`` so the subsequent write-back does not silently corrupt
    INT parameters by sending them as REAL32.
    """
    if not telemetry_service.is_connected:
        raise HTTPException(400, "No active telemetry connection")

    loop = asyncio.get_running_loop()
    fc_params = await loop.run_in_executor(None, telemetry_service.read_all_params)

    twin_params = px4_to_twin(fc_params)
    return {
        "fc_param_count": len(fc_params),
        "twin_params": twin_params,
        "subsystems_affected": list(twin_params.keys()),
        "raw_fc_params": {k: {"value": v[0], "type": v[1]} for k, v in fc_params.items()},
    }


@router.get("/logs/list-from-fc")
async def list_fc_logs() -> dict[str, Any]:
    """List on-board logs via ``LOG_REQUEST_LIST``. Requires an active FC link."""
    if not telemetry_service.is_connected:
        raise HTTPException(400, "No active telemetry connection")
    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(None, telemetry_service.list_logs)
    return {"count": len(entries), "logs": entries}


class DownloadFcLogRequest(BaseModel):
    log_id: int
    chunk_size: int = 90


@router.post("/logs/download-from-fc")
async def download_fc_log(req: DownloadFcLogRequest) -> dict[str, Any]:
    """Download a single on-board log over MAVLink.

    Runs the download on the thread-pool because the MAVLink protocol is
    synchronous. Returns the uLog / DataFlash bytes base64-encoded so
    clients can persist them; large logs should prefer a future
    streaming variant.
    """
    if not telemetry_service.is_connected:
        raise HTTPException(400, "No active telemetry connection")
    import base64

    loop = asyncio.get_running_loop()
    try:
        data = await loop.run_in_executor(
            None,
            lambda: telemetry_service.download_log(req.log_id, req.chunk_size),
        )
    except RuntimeError as exc:
        raise HTTPException(502, f"Log download failed: {exc}") from exc
    return {
        "log_id": req.log_id,
        "size_bytes": len(data),
        "base64_data": base64.b64encode(data).decode("ascii"),
    }


@router.post("/logs/erase-fc")
async def erase_fc_logs() -> dict[str, str]:
    """Erase all on-board logs (``LOG_ERASE``)."""
    if not telemetry_service.is_connected:
        raise HTTPException(400, "No active telemetry connection")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, telemetry_service.erase_logs)
    return {"status": "erased"}


class GeofenceUploadRequest(BaseModel):
    """PX4 geofence upload request.

    ``polygon`` (legacy) is treated as a single inclusion polygon. Prefer
    ``inclusion_polygons`` / ``exclusion_polygons`` for the full PX4 fence
    semantics (the FC's ``GF_*`` params still need to be set separately).
    """

    polygon: list[list[float]] | None = None
    inclusion_polygons: list[list[list[float]]] | None = None
    exclusion_polygons: list[list[list[float]]] | None = None


@router.post("/geofence/upload")
async def upload_geofence(request: GeofenceUploadRequest) -> dict[str, Any]:
    """Upload a PX4 geofence (inclusion + exclusion polygons)."""
    if not telemetry_service.is_connected:
        raise HTTPException(400, "No active telemetry connection")

    inclusions: list[list[tuple[float, float]]] = []
    exclusions: list[list[tuple[float, float]]] = []
    if request.inclusion_polygons:
        inclusions = [[(p[0], p[1]) for p in poly] for poly in request.inclusion_polygons]
    if request.exclusion_polygons:
        exclusions = [[(p[0], p[1]) for p in poly] for poly in request.exclusion_polygons]
    if request.polygon and not inclusions:
        inclusions = [[(p[0], p[1]) for p in request.polygon]]

    if not inclusions and not exclusions:
        raise HTTPException(400, "Provide at least one inclusion or exclusion polygon")
    for poly in (*inclusions, *exclusions):
        if len(poly) < 3:
            raise HTTPException(400, "Each geofence polygon needs at least 3 vertices")

    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(
        None,
        lambda: telemetry_service.upload_geofence_px4(inclusions, exclusions),
    )
    return {
        "success": ok,
        "inclusion_polygons": len(inclusions),
        "exclusion_polygons": len(exclusions),
        "message": "Geofence uploaded to FC" if ok else "Geofence upload failed",
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
