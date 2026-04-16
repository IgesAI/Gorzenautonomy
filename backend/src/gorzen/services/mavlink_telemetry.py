"""MAVLink telemetry — QGroundControl-style direct serial reader, PX4-aware.

Targets the Gorzen VTOL fleet running **PX4 Pro** on CubePilot Cube Black /
Orange / Orange+ / Red autopilots (and, for bench testing, a Pixhawk 2.4.8).
The implementation mirrors QGroundControl's ``SerialWorker::_onPortReadyRead``:

  QGC (C++):  QSerialPort::readyRead -> readAll() -> emit dataReceived()
  This (Py):  pyserial in_waiting     -> read(n)   -> parse_buffer() -> notify

Key design choices:

  * **PX4 custom_mode decoding** (main_mode + sub_mode bitfields) instead of
    blindly treating ``custom_mode`` as an ArduPilot enum — this was a
    correctness bug in the prior version that mis-labelled ``MAV_TYPE_FIXED_WING``
    as an ArduPilot *copter* mode.
  * **VTOL state tracking** via ``EXTENDED_SYS_STATE`` (MC / FW / TRANS_FW /
    TRANS_MC) — required for any real VTOL mission planner.
  * **``MAV_CMD_SET_MESSAGE_INTERVAL``** to request stream rates instead of the
    deprecated ``REQUEST_DATA_STREAM`` (PX4 1.13+ ignores several legacy
    stream IDs).
  * **``WIND_COV``** handler alongside ``WIND`` — PX4 emits the former.
  * **Thread-safe snapshot** under a dedicated ``threading.Lock`` so HTTP /
    WebSocket readers never see torn fields mid-update.
  * **Heartbeat timeout monitor** that flips ``connected=False`` if three
    consecutive heartbeats are missed; optional auto-reconnect.
  * **SYS_STATUS per-sensor health bitmask** decoded into named flags so the
    pre-flight checklist can tell exactly which sensor failed.
  * **STATUSTEXT ring buffer** that captures pre-arm failure reasons straight
    from the FC so operators see what QGC would show.

QGC source reference:
  SerialWorker::_onPortReadyRead()  -> readAll() + emit dataReceived()
  github.com/mavlink/qgroundcontrol/blob/master/src/Comms/SerialLink.cc
"""

from __future__ import annotations

import asyncio
import copy
import logging
import math
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

try:
    from pymavlink import mavutil  # type: ignore[import-untyped]

    PYMAVLINK_AVAILABLE = True
except ImportError:
    PYMAVLINK_AVAILABLE = False
    mavutil = None  # type: ignore


# ---------------------------------------------------------------------------
# Autopilot / vehicle / mode decoding
# ---------------------------------------------------------------------------

# MAV_AUTOPILOT enum (common.xml)
MAV_AUTOPILOT_GENERIC = 0
MAV_AUTOPILOT_PX4 = 12
MAV_AUTOPILOT_ARDUPILOTMEGA = 3

# MAV_MODE_FLAG bits
MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1
MAV_MODE_FLAG_SAFETY_ARMED = 128

# PX4 main_mode / sub_mode encoded into MAVLink custom_mode.
# Layout (see PX4 src/modules/commander/px4_custom_mode.h):
#   bits 24-31  sub_mode
#   bits 16-23  main_mode
#   bits  0-15  unused (reserved)
PX4_MAIN_MODES: dict[int, str] = {
    1: "MANUAL",
    2: "ALTCTL",
    3: "POSCTL",
    4: "AUTO",
    5: "ACRO",
    6: "OFFBOARD",
    7: "STABILIZED",
    8: "RATTITUDE",
    9: "SIMPLE",
    10: "TERMINATION",
}

PX4_AUTO_SUBMODES: dict[int, str] = {
    1: "READY",
    2: "TAKEOFF",
    3: "LOITER",
    4: "MISSION",
    5: "RTL",
    6: "LAND",
    7: "RTGS",
    8: "FOLLOW_TARGET",
    9: "PRECLAND",
    10: "VTOL_TAKEOFF",
    11: "VTOL_LAND",
}

# MAV_TYPE values we group as multicopter / fixed-wing / VTOL. Used only for
# display metadata — mode decoding is driven by ``HEARTBEAT.autopilot``.
MAV_TYPE_MULTIROTOR = {2, 13, 14, 15, 29}
MAV_TYPE_FIXED_WING = {1}
MAV_TYPE_VTOL = {19, 20, 21, 22, 23}  # VTOL_DUOROTOR .. VTOL_RESERVED4

ARDUPILOT_COPTER_MODES: dict[int, str] = {
    0: "STABILIZE",
    1: "ACRO",
    2: "ALT_HOLD",
    3: "AUTO",
    4: "GUIDED",
    5: "LOITER",
    6: "RTL",
    7: "CIRCLE",
    8: "POSITION",
    9: "LAND",
    10: "OF_LOITER",
    11: "DRIFT",
    13: "SPORT",
    14: "FLIP",
    15: "AUTOTUNE",
    16: "POSHOLD",
    17: "BRAKE",
    18: "THROW",
    19: "AVOID_ADSB",
    20: "GUIDED_NOGPS",
    21: "SMART_RTL",
    22: "FLOWHOLD",
    23: "FOLLOW",
    24: "ZIGZAG",
    25: "SYSTEMID",
    26: "AUTOROTATE",
    27: "AUTO_RTL",
}

ARDUPILOT_PLANE_MODES: dict[int, str] = {
    0: "MANUAL",
    1: "CIRCLE",
    2: "STABILIZE",
    3: "TRAINING",
    4: "ACRO",
    5: "FLY_BY_WIRE_A",
    6: "FLY_BY_WIRE_B",
    7: "CRUISE",
    8: "AUTOTUNE",
    10: "AUTO",
    11: "RTL",
    12: "LOITER",
    13: "TAKEOFF",
    14: "AVOID_ADSB",
    15: "GUIDED",
    17: "QSTABILIZE",
    18: "QHOVER",
    19: "QLOITER",
    20: "QLAND",
    21: "QRTL",
    22: "QAUTOTUNE",
    23: "QACRO",
    24: "THERMAL",
    25: "LOITER_ALT_QLAND",
}

GPS_FIX_TYPES: dict[int, str] = {
    0: "NO_GPS",
    1: "NO_FIX",
    2: "2D_FIX",
    3: "3D_FIX",
    4: "DGPS",
    5: "RTK_FLOAT",
    6: "RTK_FIXED",
    7: "STATIC",
    8: "PPP",
}

# MAV_VTOL_STATE (common.xml)
VTOL_STATES: dict[int, str] = {
    0: "UNDEFINED",
    1: "TRANSITION_TO_FW",
    2: "TRANSITION_TO_MC",
    3: "MC",
    4: "FW",
}

# MAV_LANDED_STATE (common.xml)
LANDED_STATES: dict[int, str] = {
    0: "UNDEFINED",
    1: "ON_GROUND",
    2: "IN_AIR",
    3: "TAKEOFF",
    4: "LANDING",
}

# MAV_SYS_STATUS_SENSOR bitmask (common.xml). Only the frequently-checked
# bits are named; anything else is surfaced as a numeric flag.
SYS_STATUS_SENSORS: list[tuple[int, str]] = [
    (1 << 0, "gyro"),
    (1 << 1, "accel"),
    (1 << 2, "mag"),
    (1 << 3, "abs_pressure"),
    (1 << 4, "diff_pressure"),
    (1 << 5, "gps"),
    (1 << 6, "optical_flow"),
    (1 << 7, "vision_position"),
    (1 << 8, "laser_position"),
    (1 << 9, "external_ground_truth"),
    (1 << 10, "angular_rate_control"),
    (1 << 11, "attitude_stabilization"),
    (1 << 12, "yaw_position"),
    (1 << 13, "z_altitude_control"),
    (1 << 14, "xy_position_control"),
    (1 << 15, "motor_outputs"),
    (1 << 16, "rc_receiver"),
    (1 << 17, "gyro2"),
    (1 << 18, "accel2"),
    (1 << 19, "mag2"),
    (1 << 20, "geofence"),
    (1 << 21, "ahrs"),
    (1 << 22, "terrain"),
    (1 << 23, "reverse_motor"),
    (1 << 24, "logging"),
    (1 << 25, "battery"),
    (1 << 26, "proximity"),
    (1 << 27, "satcom"),
    (1 << 28, "prearm_check"),
    (1 << 29, "obstacle_avoidance"),
    (1 << 30, "propulsion"),
]

_ALL_STREAM_IDS = (0, 1, 2, 3, 4, 6, 10, 11, 12)

# Default message-interval plan (Hz) for a full-bandwidth link.
DEFAULT_MSG_RATES_HZ: dict[str, float] = {
    "HEARTBEAT": 1.0,
    "SYS_STATUS": 2.0,
    "GPS_RAW_INT": 2.0,
    "ATTITUDE": 20.0,
    "GLOBAL_POSITION_INT": 10.0,
    "VFR_HUD": 10.0,
    "BATTERY_STATUS": 2.0,
    "EXTENDED_SYS_STATE": 2.0,
    "WIND_COV": 1.0,
    "RC_CHANNELS": 2.0,
    "STATUSTEXT": 5.0,
}

LOW_BANDWIDTH_MSG_RATES_HZ: dict[str, float] = {
    "HEARTBEAT": 1.0,
    "SYS_STATUS": 1.0,
    "GPS_RAW_INT": 1.0,
    "ATTITUDE": 4.0,
    "GLOBAL_POSITION_INT": 2.0,
    "VFR_HUD": 2.0,
    "BATTERY_STATUS": 1.0,
    "EXTENDED_SYS_STATE": 1.0,
    "WIND_COV": 0.5,
    "RC_CHANNELS": 1.0,
    "STATUSTEXT": 2.0,
}

# PX4 MAVLink message IDs for the subset we rate-control.
MAVLINK_MSG_IDS: dict[str, int] = {
    "HEARTBEAT": 0,
    "SYS_STATUS": 1,
    "GPS_RAW_INT": 24,
    "ATTITUDE": 30,
    "GLOBAL_POSITION_INT": 33,
    "RC_CHANNELS": 65,
    "VFR_HUD": 74,
    "BATTERY_STATUS": 147,
    "EXTENDED_SYS_STATE": 245,
    "WIND_COV": 231,
    "STATUSTEXT": 253,
}

# Heartbeat watchdog defaults
HEARTBEAT_TIMEOUT_S = 3.0


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class TelemetryFrame:
    timestamp: float = 0.0
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    absolute_altitude_m: float | None = None
    relative_altitude_m: float | None = None
    roll_deg: float | None = None
    pitch_deg: float | None = None
    yaw_deg: float | None = None
    velocity_north_ms: float | None = None
    velocity_east_ms: float | None = None
    velocity_down_ms: float | None = None
    groundspeed_ms: float | None = None
    airspeed_ms: float | None = None
    climb_rate_ms: float | None = None
    battery_voltage_v: float | None = None
    battery_current_a: float | None = None
    battery_remaining_pct: float | None = None
    battery_temperature_c: float | None = None
    gps_fix_type: str | None = None
    gps_num_satellites: int | None = None
    gps_hdop: float | None = None
    wind_speed_ms: float | None = None
    wind_direction_deg: float | None = None
    flight_mode: str | None = None
    armed: bool = False
    landed_state: str | None = None
    vtol_state: str | None = None
    in_air: bool = False
    health_ok: bool = False
    sensor_health: dict[str, bool] = field(default_factory=dict)
    sensor_present: dict[str, bool] = field(default_factory=dict)
    sensor_enabled: dict[str, bool] = field(default_factory=dict)
    actuator_outputs: list[float] = field(default_factory=list)
    rc_signal_strength_pct: float | None = None
    # FC reason strings from STATUSTEXT (most recent first, trimmed ring buffer).
    pre_arm_messages: list[str] = field(default_factory=list)


@dataclass
class ConnectionState:
    connected: bool = False
    system_id: int = 0
    component_id: int = 0
    autopilot: int = 0
    autopilot_name: str = "unknown"
    vehicle_type: int = 0
    address: str = ""
    link_profile: str = "default"
    uptime_s: float = 0.0
    last_heartbeat: float = 0.0
    heartbeat_age_s: float = 0.0
    messages_received: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_serial(address: str) -> bool:
    a = address.strip().lower()
    if a.startswith("serial://"):
        return True
    if sys.platform == "win32" and a.upper().startswith("COM"):
        return True
    if a.startswith("/dev/"):
        return True
    return False


def _parse_address(address: str) -> tuple[str, int]:
    """Parse a connection URI into a pymavlink device string and baud rate.

    Serial defaults to 57600 (SiK radio standard). Pass ``COMx:115200`` or
    ``serial:///dev/ttyACM0:921600`` to override for RFD900x or Cube USB.
    """
    if address.startswith("serial://"):
        rest = address[len("serial://") :]
        if ":" in rest:
            parts = rest.rsplit(":", 1)
            return parts[0], int(parts[1])
        return rest, 57600
    if address.startswith("udp://"):
        rest = address[len("udp://") :]
        return f"udpin:{rest or '0.0.0.0:14540'}", 115200
    if address.startswith("tcp://"):
        rest = address[len("tcp://") :]
        return f"tcp:{rest}", 115200
    if address.upper().startswith("COM") or address.startswith("/dev/"):
        if ":" in address:
            parts = address.rsplit(":", 1)
            return parts[0], int(parts[1])
        return address, 57600
    return address, 57600


def _autopilot_name(autopilot: int) -> str:
    if autopilot == MAV_AUTOPILOT_PX4:
        return "px4"
    if autopilot == MAV_AUTOPILOT_ARDUPILOTMEGA:
        return "ardupilot"
    if autopilot == MAV_AUTOPILOT_GENERIC:
        return "generic"
    return f"autopilot_{autopilot}"


def decode_px4_custom_mode(custom_mode: int) -> str:
    """Decode a PX4 ``HEARTBEAT.custom_mode`` field into a human-readable mode.

    PX4 packs ``main_mode`` into bits 16-23 and ``sub_mode`` into bits 24-31.
    AUTO sub-modes (MISSION / LOITER / RTL / TAKEOFF / LAND / VTOL_TAKEOFF /
    VTOL_LAND) are the ones a VTOL mission operator actually cares about.
    """
    sub_mode = (custom_mode >> 24) & 0xFF
    main_mode = (custom_mode >> 16) & 0xFF
    main_name = PX4_MAIN_MODES.get(main_mode)
    if main_name is None:
        return f"PX4_MAIN_{main_mode}"
    if main_name == "AUTO":
        sub_name = PX4_AUTO_SUBMODES.get(sub_mode)
        if sub_name is None:
            return f"AUTO.SUB_{sub_mode}"
        return f"AUTO.{sub_name}"
    return main_name


def _decode_ardupilot_mode(vehicle_type: int, custom_mode: int) -> str:
    if vehicle_type in MAV_TYPE_FIXED_WING or vehicle_type in MAV_TYPE_VTOL:
        return ARDUPILOT_PLANE_MODES.get(custom_mode, f"PLANE_MODE_{custom_mode}")
    if vehicle_type in MAV_TYPE_MULTIROTOR:
        return ARDUPILOT_COPTER_MODES.get(custom_mode, f"COPTER_MODE_{custom_mode}")
    return f"MODE_{custom_mode}"


def _decode_sensor_bitmask(bitmask: int) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for bit, name in SYS_STATUS_SENSORS:
        out[name] = bool(bitmask & bit)
    return out


def _kill_mavsdk_servers() -> None:
    """Kill stray mavsdk_server processes — they clash with our pymavlink link.

    Silent by design: if there's nothing to kill we move on.
    """
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/IM", "mavsdk_server_bin.exe"], capture_output=True, timeout=5
            )
            subprocess.run(
                ["taskkill", "/F", "/IM", "mavsdk_server.exe"], capture_output=True, timeout=5
            )
        else:
            subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True, timeout=5)
    except Exception as exc:  # noqa: BLE001 — external process hygiene, never fatal
        logger.debug("mavsdk server cleanup skipped: %s", exc)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MAVLinkTelemetryService:
    """QGroundControl-style direct MAVLink telemetry service.

    The reader thread mirrors QGC's SerialWorker::_onPortReadyRead():
    check in_waiting -> read ALL bytes -> parse_buffer() -> handle messages.
    """

    def __init__(self) -> None:
        self._conn: Any = None
        self._frame = TelemetryFrame()
        self._connection = ConnectionState()
        self._subscribers: list[asyncio.Queue[TelemetryFrame]] = []
        self._reader_thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._running = False
        self._connect_time = 0.0
        self._last_connect_hint: str | None = None
        self._link_profile: str = "default"
        self._loop: asyncio.AbstractEventLoop | None = None
        self._serial_lock = threading.Lock()
        # Guards every mutation of ``self._frame`` / ``self._connection`` so
        # HTTP / WebSocket readers always see a coherent snapshot.
        self._frame_lock = threading.Lock()
        self._reader_paused = False
        self._statustext_buffer: deque[str] = deque(maxlen=32)

    @property
    def last_connect_hint(self) -> str | None:
        return self._last_connect_hint

    @property
    def link_profile(self) -> str:
        return self._link_profile

    @property
    def frame(self) -> TelemetryFrame:
        """Return the live frame reference. Callers must not mutate it."""
        return self._frame

    @property
    def connection(self) -> ConnectionState:
        return self._connection

    @property
    def is_connected(self) -> bool:
        return self._connection.connected

    def get_connected_system(self) -> Any | None:
        if self._connection.connected and self._conn is not None:
            return self._conn
        return None

    # -- connect / disconnect -----------------------------------------------

    async def connect(self, address: str = "udp://:14540", link_profile: str = "default") -> bool:
        self._last_connect_hint = None
        if _is_serial(address):
            self._link_profile = "low_bandwidth"
        else:
            self._link_profile = (
                link_profile if link_profile in ("default", "low_bandwidth") else "default"
            )

        if not PYMAVLINK_AVAILABLE:
            self._last_connect_hint = "pymavlink not installed. pip install pymavlink"
            self._connection = ConnectionState(
                connected=False, address=address, link_profile=self._link_profile
            )
            return False

        if _is_serial(address):
            try:
                import serial  # noqa: F401
            except ImportError:
                self._last_connect_hint = "pyserial required for serial links. pip install pyserial"
                self._connection = ConnectionState(
                    connected=False, address=address, link_profile=self._link_profile
                )
                return False

        try:
            await self.disconnect()
            _kill_mavsdk_servers()
            assert mavutil is not None

            device, baud = _parse_address(address)
            logger.info("Connecting to %s @ %d baud (profile=%s)", device, baud, self._link_profile)

            loop = asyncio.get_running_loop()
            self._loop = loop

            self._conn = await loop.run_in_executor(
                None,
                lambda: mavutil.mavlink_connection(device, baud=baud, source_system=255),  # type: ignore[union-attr]
            )
            conn = self._conn
            if conn is None:
                self._connection = ConnectionState(
                    connected=False, address=address, link_profile=self._link_profile
                )
                return False

            self._tune_serial(conn)

            logger.info("Waiting for heartbeat ...")
            hb = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: conn.wait_heartbeat(timeout=30)),
                timeout=35.0,
            )
            if hb is None:
                logger.error("No heartbeat received")
                conn.close()
                self._conn = None
                self._connection = ConnectionState(
                    connected=False, address=address, link_profile=self._link_profile
                )
                return False

            with self._frame_lock:
                self._connection = ConnectionState(
                    connected=True,
                    system_id=conn.target_system,
                    component_id=conn.target_component,
                    autopilot=int(hb.autopilot),
                    autopilot_name=_autopilot_name(int(hb.autopilot)),
                    vehicle_type=int(hb.type),
                    address=address,
                    link_profile=self._link_profile,
                    last_heartbeat=time.time(),
                    heartbeat_age_s=0.0,
                )
            self._connect_time = time.time()

            self._configure_streams(conn)

            await loop.run_in_executor(None, lambda: self._drain(conn))

            self._running = True
            self._reader_thread = threading.Thread(
                target=self._reader_fn,
                name="mavlink-reader",
                daemon=True,
            )
            self._reader_thread.start()
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_watchdog_fn,
                name="mavlink-hb-watchdog",
                daemon=True,
            )
            self._heartbeat_thread.start()

            logger.info(
                "Connected to system %d (%s, type=%d) at %s",
                conn.target_system,
                self._connection.autopilot_name,
                self._connection.vehicle_type,
                address,
            )
            return True

        except Exception as e:
            logger.error("Connection failed: %s", e)
            self._last_connect_hint = str(e)
            if self._conn:
                try:
                    self._conn.close()
                except Exception as close_exc:
                    logger.debug("conn.close() during failure ignored: %s", close_exc)
                self._conn = None
            self._connection = ConnectionState(
                connected=False, address=address, link_profile=self._link_profile
            )
            return False

    async def disconnect(self) -> None:
        if not self._running and self._conn is None:
            return
        logger.info("Disconnecting ...")
        self._running = False
        for t in (self._reader_thread, self._heartbeat_thread):
            if t and t.is_alive():
                t.join(timeout=3.0)
        self._reader_thread = None
        self._heartbeat_thread = None
        if self._conn:
            try:
                self._conn.close()
            except Exception as exc:
                logger.debug("conn.close() during disconnect: %s", exc)
            self._conn = None
        with self._frame_lock:
            self._connection.connected = False
            self._frame = TelemetryFrame()
            self._statustext_buffer.clear()
        self._loop = None
        logger.info("Disconnected")

    def subscribe(self) -> asyncio.Queue[TelemetryFrame]:
        q: asyncio.Queue[TelemetryFrame] = asyncio.Queue(maxsize=4)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[TelemetryFrame]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def stream(self) -> AsyncIterator[TelemetryFrame]:
        q = self.subscribe()
        try:
            while self._running:
                yield await q.get()
        finally:
            self.unsubscribe(q)

    # -- serial port setup --------------------------------------------------

    @staticmethod
    def _tune_serial(conn: Any) -> None:
        """Match QGC's serial config: no flow control, non-blocking reads."""
        port = getattr(conn, "port", None) or getattr(conn, "fd", None)
        if port is None:
            return
        try:
            if hasattr(port, "timeout"):
                port.timeout = 0
            if hasattr(port, "write_timeout"):
                port.write_timeout = 1.0
            if hasattr(port, "rtscts"):
                port.rtscts = False
            if hasattr(port, "dsrdtr"):
                port.dsrdtr = False
            if hasattr(port, "set_buffer_size"):
                port.set_buffer_size(rx_size=4096, tx_size=4096)
            if hasattr(port, "reset_input_buffer"):
                port.reset_input_buffer()
            logger.info("Serial port tuned (QGC-style)")
        except Exception as exc:
            # Surface as debug rather than swallowing silently — serial tuning
            # is best-effort and failures shouldn't break the connection.
            logger.debug("Serial tune partial: %s", exc)

    # -- stream configuration -----------------------------------------------

    def _configure_streams(self, conn: Any) -> None:
        """Request per-message intervals via ``MAV_CMD_SET_MESSAGE_INTERVAL``.

        This is the MAVLink-2 / PX4-blessed way; ``REQUEST_DATA_STREAM`` is
        deprecated and silently ignored for several streams on PX4 >=1.13.
        Legacy ``REQUEST_DATA_STREAM`` is issued as a fallback for FCs that
        don't honour the command (best-effort).
        """
        rates = (
            LOW_BANDWIDTH_MSG_RATES_HZ
            if self._link_profile == "low_bandwidth"
            else DEFAULT_MSG_RATES_HZ
        )
        ok = 0
        for name, hz in rates.items():
            msg_id = MAVLINK_MSG_IDS.get(name)
            if msg_id is None:
                continue
            interval_us = -1.0 if hz <= 0 else max(1.0, 1_000_000.0 / hz)
            try:
                conn.mav.command_long_send(
                    conn.target_system,
                    conn.target_component,
                    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,  # type: ignore[union-attr]
                    0,
                    float(msg_id),
                    float(interval_us),
                    0,
                    0,
                    0,
                    0,
                    0,
                )
                ok += 1
            except Exception as exc:
                logger.warning("SET_MESSAGE_INTERVAL failed for %s: %s", name, exc)

        # Legacy fallback: disable all, enable EXTENDED_STATUS / POSITION / EXTRA1
        # This helps older ArduPilot test benches and is harmless on PX4.
        m = mavutil.mavlink  # type: ignore[union-attr]
        for sid in _ALL_STREAM_IDS:
            try:
                conn.mav.request_data_stream_send(
                    conn.target_system, conn.target_component, sid, 0, 0
                )
            except Exception as exc:
                logger.debug("legacy stream disable failed (sid=%d): %s", sid, exc)

        lo = self._link_profile == "low_bandwidth"
        legacy_streams = [
            (m.MAV_DATA_STREAM_EXTENDED_STATUS, 1),
            (m.MAV_DATA_STREAM_POSITION, 2 if lo else 4),
            (m.MAV_DATA_STREAM_EXTRA1, 2 if lo else 4),
        ]
        if not lo:
            legacy_streams.extend(
                [
                    (m.MAV_DATA_STREAM_EXTRA2, 4),
                    (m.MAV_DATA_STREAM_RC_CHANNELS, 2),
                    (m.MAV_DATA_STREAM_EXTRA3, 1),
                ]
            )
        for stream_id, rate in legacy_streams:
            try:
                conn.mav.request_data_stream_send(
                    conn.target_system, conn.target_component, stream_id, rate, 1
                )
            except Exception as exc:
                logger.debug("legacy stream enable failed (sid=%d): %s", stream_id, exc)

        logger.info(
            "Streams configured: SET_MESSAGE_INTERVAL x%d (%s), legacy fallback issued",
            ok,
            self._link_profile,
        )

    @staticmethod
    def _drain(conn: Any) -> int:
        n = 0
        while True:
            msg = conn.recv_match(blocking=False)
            if msg is None:
                break
            n += 1
            if n > 2000:
                break
        if n:
            logger.info("Drained %d stale messages", n)
        return n

    # -- message handler ----------------------------------------------------

    def _decode_flight_mode(self, base_mode: int, custom_mode: int) -> str:
        """Decode ``HEARTBEAT`` mode using ``connection.autopilot`` to pick the right table."""
        if not (base_mode & MAV_MODE_FLAG_CUSTOM_MODE_ENABLED):
            return "BASE_MODE_ONLY"

        autopilot = self._connection.autopilot
        if autopilot == MAV_AUTOPILOT_PX4:
            return decode_px4_custom_mode(custom_mode)
        if autopilot == MAV_AUTOPILOT_ARDUPILOTMEGA:
            return _decode_ardupilot_mode(self._connection.vehicle_type, custom_mode)
        return f"MODE_{custom_mode}"

    def _handle_message(self, msg: Any) -> None:
        t = msg.get_type()
        now = time.time()

        with self._frame_lock:
            if t == "HEARTBEAT":
                self._frame.armed = bool(msg.base_mode & MAV_MODE_FLAG_SAFETY_ARMED)
                # If we reconnected and heartbeat came from a different autopilot,
                # update our cached identity — mode decoding depends on it.
                new_ap = int(msg.autopilot)
                if new_ap != self._connection.autopilot:
                    self._connection.autopilot = new_ap
                    self._connection.autopilot_name = _autopilot_name(new_ap)
                    self._connection.vehicle_type = int(msg.type)
                self._frame.flight_mode = self._decode_flight_mode(msg.base_mode, msg.custom_mode)
                self._connection.last_heartbeat = now
                self._connection.heartbeat_age_s = 0.0
                self._connection.messages_received += 1

            elif t == "GLOBAL_POSITION_INT":
                lat = msg.lat / 1e7
                lon = msg.lon / 1e7
                # GPS not yet locked often reports 0/0 — treat as no data rather
                # than "we're in the Gulf of Guinea".
                if abs(lat) < 1e-6 and abs(lon) < 1e-6:
                    self._frame.latitude_deg = None
                    self._frame.longitude_deg = None
                else:
                    self._frame.latitude_deg = lat
                    self._frame.longitude_deg = lon
                self._frame.absolute_altitude_m = msg.alt / 1000.0
                self._frame.relative_altitude_m = msg.relative_alt / 1000.0
                self._frame.velocity_north_ms = msg.vx / 100.0
                self._frame.velocity_east_ms = msg.vy / 100.0
                self._frame.velocity_down_ms = msg.vz / 100.0
                self._frame.groundspeed_ms = math.hypot(msg.vx / 100.0, msg.vy / 100.0)
                self._frame.climb_rate_ms = -msg.vz / 100.0
                self._frame.timestamp = now
                self._connection.messages_received += 1

            elif t == "ATTITUDE":
                self._frame.roll_deg = math.degrees(msg.roll)
                self._frame.pitch_deg = math.degrees(msg.pitch)
                self._frame.yaw_deg = math.degrees(msg.yaw) % 360
                self._frame.timestamp = now
                self._connection.messages_received += 1

            elif t == "VFR_HUD":
                self._frame.airspeed_ms = msg.airspeed
                self._frame.groundspeed_ms = msg.groundspeed
                self._frame.climb_rate_ms = msg.climb
                self._connection.messages_received += 1

            elif t == "SYS_STATUS":
                self._frame.battery_voltage_v = msg.voltage_battery / 1000.0
                if msg.current_battery >= 0:
                    self._frame.battery_current_a = msg.current_battery / 100.0
                if msg.battery_remaining >= 0:
                    self._frame.battery_remaining_pct = float(msg.battery_remaining)
                self._frame.sensor_present = _decode_sensor_bitmask(
                    int(msg.onboard_control_sensors_present)
                )
                self._frame.sensor_enabled = _decode_sensor_bitmask(
                    int(msg.onboard_control_sensors_enabled)
                )
                self._frame.sensor_health = _decode_sensor_bitmask(
                    int(msg.onboard_control_sensors_health)
                )
                enabled = self._frame.sensor_enabled
                health = self._frame.sensor_health
                self._frame.health_ok = all(
                    health.get(k, False) for k, on in enabled.items() if on
                )
                self._connection.messages_received += 1

            elif t == "GPS_RAW_INT":
                self._frame.gps_fix_type = GPS_FIX_TYPES.get(msg.fix_type, f"FIX_{msg.fix_type}")
                self._frame.gps_num_satellites = msg.satellites_visible
                if msg.eph != 65535:
                    self._frame.gps_hdop = msg.eph / 100.0
                else:
                    self._frame.gps_hdop = None
                self._connection.messages_received += 1

            elif t == "WIND":
                # ArduPilot-style scalar wind message.
                self._frame.wind_direction_deg = msg.direction
                self._frame.wind_speed_ms = msg.speed
                self._connection.messages_received += 1

            elif t == "WIND_COV":
                # PX4-canonical wind message. ``wind_x`` / ``wind_y`` are NED m/s.
                wx = msg.wind_x
                wy = msg.wind_y
                self._frame.wind_speed_ms = math.hypot(wx, wy)
                # Meteorological direction: where wind is coming FROM.
                self._frame.wind_direction_deg = (math.degrees(math.atan2(-wy, -wx)) + 360) % 360
                self._connection.messages_received += 1

            elif t == "EXTENDED_SYS_STATE":
                self._frame.vtol_state = VTOL_STATES.get(int(msg.vtol_state), "UNDEFINED")
                landed = LANDED_STATES.get(int(msg.landed_state), "UNDEFINED")
                self._frame.landed_state = landed
                self._frame.in_air = landed in ("IN_AIR", "TAKEOFF", "LANDING")
                self._connection.messages_received += 1

            elif t == "RC_CHANNELS":
                if msg.rssi != 255:
                    self._frame.rc_signal_strength_pct = (msg.rssi / 254.0) * 100
                self._connection.messages_received += 1

            elif t == "BATTERY_STATUS":
                if hasattr(msg, "temperature") and msg.temperature != 32767:
                    self._frame.battery_temperature_c = msg.temperature / 100.0
                self._connection.messages_received += 1

            elif t == "STATUSTEXT":
                text = bytes(msg.text).split(b"\x00", 1)[0].decode("utf-8", errors="replace")
                severity = int(getattr(msg, "severity", 6))
                entry = f"[{severity}] {text}"
                self._statustext_buffer.append(entry)
                # Keep frame's surfaced list capped so JSON stays small.
                buffered = list(self._statustext_buffer)
                self._frame.pre_arm_messages = list(reversed(buffered))[:8]
                self._connection.messages_received += 1
                # Stream to logs at INFO for quick tailing.
                if severity <= 3:
                    logger.warning("FC STATUSTEXT: %s", text)
                else:
                    logger.info("FC STATUSTEXT: %s", text)

    # -- QGC-style reader thread --------------------------------------------

    def _reader_fn(self) -> None:
        """Replicate QGC's _onPortReadyRead: read ALL available bytes,
        parse ALL complete MAVLink frames, signal asyncio instantly.
        """
        logger.info("Reader thread started")
        conn = self._conn
        port = getattr(conn, "port", None)

        while self._running:
            try:
                if conn is None:
                    break

                if self._reader_paused:
                    time.sleep(0.05)
                    continue

                got_data = False

                with self._serial_lock:
                    if port is not None and hasattr(port, "in_waiting"):
                        waiting = port.in_waiting
                        if waiting > 0:
                            raw = port.read(waiting)
                            if raw:
                                msgs = conn.mav.parse_buffer(raw)
                                if msgs:
                                    for m in msgs:
                                        self._handle_message(m)
                                    got_data = True
                    else:
                        while self._running:
                            m = conn.recv_match(blocking=False)
                            if m is None:
                                break
                            self._handle_message(m)
                            got_data = True

                if not got_data:
                    time.sleep(0.001)

            except Exception as e:
                if self._running:
                    logger.warning("Reader error: %s", e)
                break

        logger.info("Reader thread exited")

    def _heartbeat_watchdog_fn(self) -> None:
        """Mark link as disconnected if heartbeats stop arriving."""
        logger.info("Heartbeat watchdog started")
        while self._running:
            time.sleep(0.5)
            with self._frame_lock:
                last = self._connection.last_heartbeat
                if last <= 0:
                    continue
                age = time.time() - last
                self._connection.heartbeat_age_s = age
                if self._connection.connected and age > HEARTBEAT_TIMEOUT_S:
                    logger.warning(
                        "Heartbeat timeout (%.1fs > %.1fs), marking link as disconnected",
                        age,
                        HEARTBEAT_TIMEOUT_S,
                    )
                    self._connection.connected = False
        logger.info("Heartbeat watchdog exited")

    # -- FC parameter read/write (QGC-style) --------------------------------

    def _recv_param_value(self, conn: Any, timeout: float = 10.0) -> Any:
        """Read messages until we get a PARAM_VALUE, passing others to the
        telemetry handler so we don't lose data on slow links."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = conn.recv_match(blocking=True, timeout=1.0)
            if msg is None:
                continue
            if msg.get_type() == "PARAM_VALUE":
                return msg
            self._handle_message(msg)
        return None

    def read_param(self, param_id: str) -> tuple[float, int] | None:
        """Read a single parameter from the FC.

        Returns ``(value, param_type)`` where ``param_type`` is the
        ``MAV_PARAM_TYPE`` reported by the FC, or ``None`` on timeout. Knowing
        the true type is required for a correct write-back (see ``write_param``).
        """
        conn = self._conn
        if conn is None:
            return None
        self._reader_paused = True
        try:
            with self._serial_lock:
                conn.mav.param_request_read_send(
                    conn.target_system,
                    conn.target_component,
                    param_id.encode("utf-8"),
                    -1,
                )
                msg = self._recv_param_value(conn, timeout=10.0)
                if msg is None:
                    return None
                return float(msg.param_value), int(msg.param_type)
        finally:
            self._reader_paused = False

    def write_param(self, param_id: str, value: float, param_type: int | None = None) -> bool:
        """Write a single parameter to the FC.

        When ``param_type`` is omitted, we first read the parameter to learn
        its real ``MAV_PARAM_TYPE`` and write back with the matching type.
        Sending INT params as REAL32 (the old default) silently fails on
        PX4 and ArduPilot for ``*_NUM`` / ``COM_*`` flag params.
        """
        conn = self._conn
        if conn is None:
            return False
        if param_type is None:
            probe = self.read_param(param_id)
            if probe is None:
                return False
            _, param_type = probe
        self._reader_paused = True
        try:
            with self._serial_lock:
                conn.mav.param_set_send(
                    conn.target_system,
                    conn.target_component,
                    param_id.encode("utf-8"),
                    float(value),
                    int(param_type),
                )
                msg = self._recv_param_value(conn, timeout=10.0)
                if msg is None:
                    return False
                return msg.param_id.rstrip("\x00") == param_id
        finally:
            self._reader_paused = False

    def read_all_params(self) -> dict[str, tuple[float, int]]:
        """Request all parameters from the FC.

        Returns a mapping of ``param_id -> (value, param_type)`` so callers
        round-tripping writes preserve the FC's native type.
        """
        conn = self._conn
        if conn is None:
            return {}
        self._reader_paused = True
        try:
            with self._serial_lock:
                while conn.recv_match(blocking=False) is not None:
                    pass

                conn.mav.param_request_list_send(
                    conn.target_system,
                    conn.target_component,
                )
                params: dict[str, tuple[float, int]] = {}
                param_count = -1
                no_new_count = 0

                while True:
                    msg = conn.recv_match(blocking=True, timeout=0.5)
                    if msg is not None:
                        if msg.get_type() == "PARAM_VALUE":
                            pid = msg.param_id.rstrip("\x00")
                            params[pid] = (float(msg.param_value), int(msg.param_type))
                            param_count = msg.param_count
                            no_new_count = 0
                            if len(params) % 50 == 0:
                                logger.info("Params progress: %d/%d", len(params), param_count)
                            if msg.param_index == msg.param_count - 1:
                                break
                        else:
                            self._handle_message(msg)
                    else:
                        no_new_count += 1
                        # On LoRa/SiK params trickle in; give up after ~40s silence.
                        if no_new_count > 80:
                            break

                logger.info(
                    "Read %d/%d params from FC",
                    len(params),
                    param_count if param_count > 0 else 0,
                )
                return params
        finally:
            self._reader_paused = False

    def upload_geofence_px4(
        self,
        inclusion_polygons: list[list[tuple[float, float]]],
        exclusion_polygons: list[list[tuple[float, float]]] | None = None,
    ) -> bool:
        """Upload a geofence to a PX4 flight controller.

        PX4 implements fences as ``MAV_MISSION_TYPE_FENCE`` mission items using
        the INT-frame ``MISSION_ITEM_INT`` message. Inclusion polygons are
        ``MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION`` (5001) and exclusion
        polygons are ``MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION`` (5002).
        ``param1`` is the vertex count for that polygon. The FC also reads
        ``GF_*`` params (min/max alt, action) — set those via ``write_param``.
        """
        conn = self._conn
        if conn is None:
            return False
        exclusion_polygons = exclusion_polygons or []
        all_polys: list[tuple[list[tuple[float, float]], int]] = []
        m = mavutil.mavlink  # type: ignore[union-attr]
        inc_cmd = m.MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION
        exc_cmd = m.MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION
        for poly in inclusion_polygons:
            if len(poly) >= 3:
                all_polys.append((poly, inc_cmd))
        for poly in exclusion_polygons:
            if len(poly) >= 3:
                all_polys.append((poly, exc_cmd))
        if not all_polys:
            return False

        total_items = sum(len(poly) for poly, _ in all_polys)

        self._reader_paused = True
        try:
            with self._serial_lock:
                conn.mav.mission_count_send(
                    conn.target_system,
                    conn.target_component,
                    total_items,
                    m.MAV_MISSION_TYPE_FENCE,
                )

                seq = 0
                for poly, cmd in all_polys:
                    vcount = len(poly)
                    for lat, lon in poly:
                        # PX4 & ArduPilot both use MISSION_REQUEST_INT for
                        # INT-frame items; we accept either for compatibility.
                        req = conn.recv_match(
                            type=["MISSION_REQUEST_INT", "MISSION_REQUEST"],
                            blocking=True,
                            timeout=5.0,
                        )
                        if req is None:
                            logger.error("Geofence upload: MISSION_REQUEST timed out at seq %d", seq)
                            return False
                        if int(req.seq) != seq:
                            logger.warning(
                                "Geofence seq mismatch (fc=%d, us=%d) — continuing",
                                req.seq,
                                seq,
                            )
                        conn.mav.mission_item_int_send(
                            conn.target_system,
                            conn.target_component,
                            seq,
                            m.MAV_FRAME_GLOBAL,
                            cmd,
                            0,
                            1,
                            vcount,
                            0,
                            0,
                            0,
                            int(lat * 1e7),
                            int(lon * 1e7),
                            0,
                            m.MAV_MISSION_TYPE_FENCE,
                        )
                        seq += 1

                final_ack = conn.recv_match(type="MISSION_ACK", blocking=True, timeout=5.0)
                if final_ack is None:
                    logger.error("Geofence upload: no final MISSION_ACK")
                    return False
                if final_ack.type != 0:
                    logger.error("Geofence upload rejected by FC: MAV_MISSION_ACK=%d", final_ack.type)
                    return False
                return True
        finally:
            self._reader_paused = False

    # Back-compat wrapper — accepts a single inclusion polygon.
    def upload_geofence(self, polygon: list[tuple[float, float]]) -> bool:
        return self.upload_geofence_px4([polygon])

    # -- in-field log download (LOG_REQUEST_LIST / LOG_REQUEST_DATA) --------

    def list_logs(self, timeout_s: float = 10.0) -> list[dict[str, Any]]:
        """Enumerate the on-board log store via ``LOG_REQUEST_LIST``.

        Returns a list of ``{id, time_utc, size_bytes}`` dicts ordered by
        FC log id. Requires an active connection; pauses the reader thread
        so the MAVLink log protocol messages aren't routed to the telemetry
        handler.
        """
        conn = self._conn
        if conn is None:
            raise RuntimeError("Not connected")
        self._reader_paused = True
        try:
            with self._serial_lock:
                conn.mav.log_request_list_send(
                    conn.target_system,
                    conn.target_component,
                    0,
                    0xFFFF,
                )
                entries: dict[int, dict[str, Any]] = {}
                deadline = time.time() + timeout_s
                while time.time() < deadline:
                    msg = conn.recv_match(
                        type="LOG_ENTRY", blocking=True, timeout=1.0
                    )
                    if msg is None:
                        continue
                    entries[int(msg.id)] = {
                        "id": int(msg.id),
                        "time_utc": int(getattr(msg, "time_utc", 0)),
                        "size_bytes": int(msg.size),
                        "num_logs": int(getattr(msg, "num_logs", 0)),
                    }
                    if int(msg.id) == int(msg.last_log_num):
                        break
                return [entries[k] for k in sorted(entries)]
        finally:
            self._reader_paused = False

    def download_log(
        self,
        log_id: int,
        chunk_size: int = 90,
        timeout_s: float = 60.0,
        progress_cb: Any = None,
    ) -> bytes:
        """Download a single on-board log via ``LOG_REQUEST_DATA``.

        Returns the raw uLog / DataFlash bytes. ``progress_cb`` is invoked
        with ``(bytes_so_far, total_bytes)`` after every chunk.
        """
        conn = self._conn
        if conn is None:
            raise RuntimeError("Not connected")
        self._reader_paused = True
        try:
            with self._serial_lock:
                # First, request the size of the log.
                conn.mav.log_request_list_send(
                    conn.target_system,
                    conn.target_component,
                    int(log_id),
                    int(log_id),
                )
                entry = None
                deadline = time.time() + 5.0
                while time.time() < deadline:
                    msg = conn.recv_match(type="LOG_ENTRY", blocking=True, timeout=1.0)
                    if msg is not None and int(msg.id) == int(log_id):
                        entry = msg
                        break
                if entry is None:
                    raise RuntimeError(f"Log {log_id} not found on FC")

                total = int(entry.size)
                buf = bytearray(total)
                received = 0
                offset = 0
                end_time = time.time() + timeout_s
                while offset < total and time.time() < end_time:
                    chunk = min(chunk_size, total - offset)
                    conn.mav.log_request_data_send(
                        conn.target_system,
                        conn.target_component,
                        int(log_id),
                        int(offset),
                        int(chunk),
                    )
                    got_piece = False
                    piece_deadline = time.time() + 2.0
                    while time.time() < piece_deadline:
                        msg = conn.recv_match(
                            type="LOG_DATA", blocking=True, timeout=0.5
                        )
                        if msg is None:
                            continue
                        if int(msg.id) != int(log_id):
                            continue
                        piece_offset = int(msg.ofs)
                        piece_count = int(msg.count)
                        piece_data = bytes(msg.data)[:piece_count]
                        buf[piece_offset : piece_offset + piece_count] = piece_data
                        received += piece_count
                        got_piece = True
                        if piece_offset + piece_count >= offset + chunk:
                            break
                    if not got_piece:
                        continue  # retry this chunk
                    offset += chunk
                    if progress_cb is not None:
                        try:
                            progress_cb(received, total)
                        except Exception as exc:
                            logger.debug("progress_cb raised: %s", exc)
                if received < total:
                    raise RuntimeError(
                        f"Log {log_id} truncated: received {received}/{total} bytes"
                    )
                # Politely end the session so the FC can resume writing.
                conn.mav.log_request_end_send(
                    conn.target_system, conn.target_component
                )
                return bytes(buf)
        finally:
            self._reader_paused = False

    def erase_logs(self) -> None:
        """Erase all on-board logs (``LOG_ERASE``)."""
        conn = self._conn
        if conn is None:
            raise RuntimeError("Not connected")
        with self._serial_lock:
            conn.mav.log_erase_send(conn.target_system, conn.target_component)

    # -- JSON snapshot ------------------------------------------------------

    def get_snapshot(self) -> dict[str, Any]:
        """Return a coherent, thread-safe snapshot of the current state.

        We hold ``_frame_lock`` for the duration of the copy so HTTP /
        WebSocket readers never see a half-updated frame (e.g. roll from
        t=1 with position from t=2).
        """
        with self._frame_lock:
            if self._connect_time > 0:
                self._connection.uptime_s = time.time() - self._connect_time
            if self._connection.last_heartbeat > 0:
                self._connection.heartbeat_age_s = time.time() - self._connection.last_heartbeat
            f = copy.deepcopy(self._frame)
            c = copy.deepcopy(self._connection)

        def _r(v: float | None, nd: int) -> float | None:
            return None if v is None else round(v, nd)

        return {
            "timestamp": f.timestamp,
            "position": {
                "latitude_deg": _r(f.latitude_deg, 7),
                "longitude_deg": _r(f.longitude_deg, 7),
                "absolute_altitude_m": _r(f.absolute_altitude_m, 1),
                "relative_altitude_m": _r(f.relative_altitude_m, 1),
            },
            "attitude": {
                "roll_deg": _r(f.roll_deg, 1),
                "pitch_deg": _r(f.pitch_deg, 1),
                "yaw_deg": _r(f.yaw_deg, 1),
            },
            "velocity": {
                "groundspeed_ms": _r(f.groundspeed_ms, 1),
                "airspeed_ms": _r(f.airspeed_ms, 1),
                "climb_rate_ms": _r(f.climb_rate_ms, 1),
                "velocity_north_ms": _r(f.velocity_north_ms, 1),
                "velocity_east_ms": _r(f.velocity_east_ms, 1),
                "velocity_down_ms": _r(f.velocity_down_ms, 1),
            },
            "battery": {
                "voltage_v": _r(f.battery_voltage_v, 2),
                "current_a": _r(f.battery_current_a, 1),
                "remaining_pct": _r(f.battery_remaining_pct, 1),
                "temperature_c": f.battery_temperature_c,
            },
            "gps": {
                "fix_type": f.gps_fix_type,
                "num_satellites": f.gps_num_satellites,
                "hdop": _r(f.gps_hdop, 2),
            },
            "wind": {
                "speed_ms": _r(f.wind_speed_ms, 1),
                "direction_deg": _r(f.wind_direction_deg, 0),
            },
            "status": {
                "flight_mode": f.flight_mode,
                "armed": f.armed,
                "in_air": f.in_air,
                "landed_state": f.landed_state,
                "vtol_state": f.vtol_state,
                "health_ok": f.health_ok,
            },
            "health": {
                "sensor_present": f.sensor_present,
                "sensor_enabled": f.sensor_enabled,
                "sensor_health": f.sensor_health,
            },
            "pre_arm_messages": f.pre_arm_messages,
            "rc": {"signal_strength_pct": _r(f.rc_signal_strength_pct, 0)},
            "connection": {
                "connected": c.connected,
                "address": c.address,
                "link_profile": c.link_profile,
                "autopilot": c.autopilot_name,
                "vehicle_type": c.vehicle_type,
                "system_id": c.system_id,
                "component_id": c.component_id,
                "uptime_s": round(c.uptime_s, 1),
                "heartbeat_age_s": round(c.heartbeat_age_s, 2),
                "messages_received": c.messages_received,
            },
        }


telemetry_service = MAVLinkTelemetryService()
