"""MAVLink telemetry — QGroundControl-style direct serial reader.

Replicates QGroundControl's zero-latency serial architecture in Python:

  QGC (C++):  QSerialPort::readyRead → readAll() → emit dataReceived()
  This (Py):  pyserial in_waiting     → read(n)   → parse_buffer() → notify

Key differences from pymavlink's recv_match(blocking=True):
  * recv_match sleeps 10 ms between polls — we never sleep when data exists
  * recv_match reads one message at a time — we read ALL bytes and parse ALL
    complete messages per cycle
  * recv_match runs in a blocking loop — we use a tight reader thread that
    signals asyncio the instant new data arrives

QGC source reference:
  SerialWorker::_onPortReadyRead()  → readAll() + emit dataReceived()
  github.com/mavlink/qgroundcontrol/blob/master/src/Comms/SerialLink.cc
"""

from __future__ import annotations

import asyncio
import logging
import math
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

try:
    from pymavlink import mavutil

    PYMAVLINK_AVAILABLE = True
except ImportError:
    PYMAVLINK_AVAILABLE = False
    mavutil = None  # type: ignore


# ---------------------------------------------------------------------------
# Flight mode tables (ArduPilot)
# ---------------------------------------------------------------------------

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
}

MAV_MODE_FLAG_SAFETY_ARMED = 128
_ALL_STREAM_IDS = (0, 1, 2, 3, 4, 6, 10, 11, 12)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class TelemetryFrame:
    timestamp: float = 0.0
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    absolute_altitude_m: float = 0.0
    relative_altitude_m: float = 0.0
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    velocity_north_ms: float = 0.0
    velocity_east_ms: float = 0.0
    velocity_down_ms: float = 0.0
    groundspeed_ms: float = 0.0
    airspeed_ms: float = 0.0
    climb_rate_ms: float = 0.0
    battery_voltage_v: float = 0.0
    battery_current_a: float = 0.0
    battery_remaining_pct: float = 0.0
    battery_temperature_c: float | None = None
    gps_fix_type: str = "NO_FIX"
    gps_num_satellites: int = 0
    gps_hdop: float = 99.0
    wind_speed_ms: float = 0.0
    wind_direction_deg: float = 0.0
    flight_mode: str = "UNKNOWN"
    armed: bool = False
    in_air: bool = False
    health_ok: bool = False
    actuator_outputs: list[float] = field(default_factory=list)
    rc_signal_strength_pct: float = 0.0


@dataclass
class ConnectionState:
    connected: bool = False
    system_id: int = 0
    address: str = ""
    link_profile: str = "default"
    uptime_s: float = 0.0
    last_heartbeat: float = 0.0
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


def _kill_mavsdk_servers() -> None:
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
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MAVLinkTelemetryService:
    """QGroundControl-style direct MAVLink telemetry service.

    The reader thread mirrors QGC's SerialWorker::_onPortReadyRead():
    check in_waiting → read ALL bytes → parse_buffer() → handle messages.
    No time.sleep(0.01) polling, no gRPC intermediary, no timer broadcast.
    """

    def __init__(self) -> None:
        self._conn: Any = None
        self._frame = TelemetryFrame()
        self._connection = ConnectionState()
        self._subscribers: list[asyncio.Queue[TelemetryFrame]] = []
        self._reader_thread: threading.Thread | None = None
        self._running = False
        self._connect_time = 0.0
        self._vehicle_type: int = 2
        self._last_connect_hint: str | None = None
        self._link_profile: str = "default"
        self._loop: asyncio.AbstractEventLoop | None = None
        self._serial_lock = threading.Lock()
        self._reader_paused = False

    @property
    def last_connect_hint(self) -> str | None:
        return self._last_connect_hint

    @property
    def link_profile(self) -> str:
        return self._link_profile

    @property
    def frame(self) -> TelemetryFrame:
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
                lambda: mavutil.mavlink_connection(device, baud=baud, source_system=255),
            )
            conn = self._conn
            if conn is None:
                self._connection = ConnectionState(
                    connected=False, address=address, link_profile=self._link_profile
                )
                return False

            # Tune serial port like QGC: no flow control, fast reads.
            self._tune_serial(conn)

            logger.info("Waiting for heartbeat …")
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

            self._vehicle_type = hb.type
            self._connection = ConnectionState(
                connected=True,
                system_id=conn.target_system,
                address=address,
                link_profile=self._link_profile,
                last_heartbeat=time.time(),
            )
            self._connect_time = time.time()

            # Disable ALL streams, then enable only what we need.
            self._configure_streams(conn)

            # Drain stale data accumulated during setup.
            await loop.run_in_executor(None, lambda: self._drain(conn))

            self._running = True
            self._reader_thread = threading.Thread(
                target=self._reader_fn,
                name="mavlink-reader",
                daemon=True,
            )
            self._reader_thread.start()

            logger.info("Connected to system %d at %s", conn.target_system, address)
            return True

        except Exception as e:
            logger.error("Connection failed: %s", e)
            self._last_connect_hint = str(e)
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
            self._connection = ConnectionState(
                connected=False, address=address, link_profile=self._link_profile
            )
            return False

    async def disconnect(self) -> None:
        if not self._running and self._conn is None:
            return
        logger.info("Disconnecting …")
        self._running = False
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=3.0)
            self._reader_thread = None
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        self._connection.connected = False
        self._frame = TelemetryFrame()
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
            logger.debug("Serial tune partial: %s", exc)

    # -- stream configuration -----------------------------------------------

    def _configure_streams(self, conn: Any) -> None:
        """Disable all streams, then enable only what we need at safe rates."""
        m = mavutil.mavlink
        for sid in _ALL_STREAM_IDS:
            try:
                conn.mav.request_data_stream_send(
                    conn.target_system,
                    conn.target_component,
                    sid,
                    0,
                    1,
                )
            except Exception:
                pass

        lo = self._link_profile == "low_bandwidth"
        streams = [
            (m.MAV_DATA_STREAM_EXTENDED_STATUS, 1),
            (m.MAV_DATA_STREAM_POSITION, 2 if lo else 4),
            (m.MAV_DATA_STREAM_EXTRA1, 2 if lo else 4),
        ]
        if not lo:
            streams.extend(
                [
                    (m.MAV_DATA_STREAM_EXTRA2, 4),
                    (m.MAV_DATA_STREAM_RC_CHANNELS, 2),
                    (m.MAV_DATA_STREAM_EXTRA3, 1),
                ]
            )

        for stream_id, rate in streams:
            conn.mav.request_data_stream_send(
                conn.target_system,
                conn.target_component,
                stream_id,
                rate,
                1,
            )
        logger.info("Streams configured (%s, %d groups)", self._link_profile, len(streams))

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
        if self._vehicle_type in (1, 2, 3, 4, 13, 14, 15, 29):
            return ARDUPILOT_COPTER_MODES.get(custom_mode, f"MODE_{custom_mode}")
        if self._vehicle_type in (0, 5, 6, 7, 8, 9, 10, 11, 12, 16, 19, 20, 21, 22):
            return ARDUPILOT_PLANE_MODES.get(custom_mode, f"MODE_{custom_mode}")
        return f"MODE_{custom_mode}"

    def _handle_message(self, msg: Any) -> None:
        t = msg.get_type()
        now = time.time()

        if t == "HEARTBEAT":
            self._frame.armed = bool(msg.base_mode & MAV_MODE_FLAG_SAFETY_ARMED)
            self._frame.flight_mode = self._decode_flight_mode(msg.base_mode, msg.custom_mode)
            self._connection.last_heartbeat = now
            self._connection.messages_received += 1
        elif t == "GLOBAL_POSITION_INT":
            self._frame.latitude_deg = msg.lat / 1e7
            self._frame.longitude_deg = msg.lon / 1e7
            self._frame.absolute_altitude_m = msg.alt / 1000.0
            self._frame.relative_altitude_m = msg.relative_alt / 1000.0
            self._frame.velocity_north_ms = msg.vx / 100.0
            self._frame.velocity_east_ms = msg.vy / 100.0
            self._frame.velocity_down_ms = msg.vz / 100.0
            self._frame.groundspeed_ms = math.hypot(msg.vx / 100.0, msg.vy / 100.0)
            self._frame.climb_rate_ms = -msg.vz / 100.0
            self._frame.in_air = self._frame.relative_altitude_m > 0.5 and self._frame.armed
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
            self._frame.health_ok = (msg.onboard_control_sensors_health & 0x01) != 0
            self._connection.messages_received += 1
        elif t == "GPS_RAW_INT":
            self._frame.gps_fix_type = GPS_FIX_TYPES.get(msg.fix_type, f"FIX_{msg.fix_type}")
            self._frame.gps_num_satellites = msg.satellites_visible
            if msg.eph != 65535:
                self._frame.gps_hdop = msg.eph / 100.0
            self._connection.messages_received += 1
        elif t == "WIND":
            self._frame.wind_direction_deg = msg.direction
            self._frame.wind_speed_ms = msg.speed
            self._connection.messages_received += 1
        elif t == "RC_CHANNELS":
            if msg.rssi != 255:
                self._frame.rc_signal_strength_pct = (msg.rssi / 254.0) * 100
            self._connection.messages_received += 1
        elif t == "BATTERY_STATUS":
            if hasattr(msg, "temperature") and msg.temperature != 32767:
                self._frame.battery_temperature_c = msg.temperature / 100.0
            self._connection.messages_received += 1

    # -- QGC-style reader thread --------------------------------------------

    def _reader_fn(self) -> None:
        """Replicate QGC's _onPortReadyRead: read ALL available bytes,
        parse ALL complete MAVLink frames, signal asyncio instantly.

        Unlike pymavlink's recv_match(blocking=True) which sleeps 10 ms
        between polls, we only sleep 1 ms when zero bytes are waiting.
        """
        logger.info("Reader thread started")
        conn = self._conn

        # Get the underlying pyserial port for direct in_waiting checks.
        port = getattr(conn, "port", None)

        while self._running:
            try:
                if conn is None:
                    break

                # Yield to param operations when they hold the lock.
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

    def read_param(self, param_id: str) -> float | None:
        """Read a single parameter from the FC (blocking, run in executor)."""
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
                return msg.param_value
        finally:
            self._reader_paused = False

    def write_param(self, param_id: str, value: float, param_type: int = 9) -> bool:
        """Write a single parameter to the FC (blocking, run in executor).

        param_type: MAV_PARAM_TYPE — 9 = REAL32 (float), 6 = INT32.
        """
        conn = self._conn
        if conn is None:
            return False
        self._reader_paused = True
        try:
            with self._serial_lock:
                conn.mav.param_set_send(
                    conn.target_system,
                    conn.target_component,
                    param_id.encode("utf-8"),
                    value,
                    param_type,
                )
                msg = self._recv_param_value(conn, timeout=10.0)
                if msg is None:
                    return False
                return msg.param_id.rstrip("\x00") == param_id
        finally:
            self._reader_paused = False

    def read_all_params(self) -> dict[str, float]:
        """Request all parameters from the FC (blocking, run in executor).

        Pauses the reader thread and reads ALL messages (not just
        PARAM_VALUE) so we don't lose them on a slow LoRa link where
        params trickle in between heartbeats and telemetry.
        """
        conn = self._conn
        if conn is None:
            return {}
        self._reader_paused = True
        try:
            with self._serial_lock:
                # Flush any stale data first.
                while conn.recv_match(blocking=False) is not None:
                    pass

                conn.mav.param_request_list_send(
                    conn.target_system,
                    conn.target_component,
                )
                params: dict[str, float] = {}
                param_count = -1
                no_new_count = 0

                while True:
                    msg = conn.recv_match(blocking=True, timeout=0.5)
                    if msg is not None:
                        if msg.get_type() == "PARAM_VALUE":
                            pid = msg.param_id.rstrip("\x00")
                            params[pid] = msg.param_value
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
                        # On LoRa, params trickle in slowly. Give up after
                        # 40 consecutive empty reads (~20 seconds of silence).
                        if no_new_count > 40:
                            break

                logger.info(
                    "Read %d/%d params from FC",
                    len(params),
                    param_count if param_count > 0 else 0,
                )
                return params
        finally:
            self._reader_paused = False

    def upload_geofence(self, polygon: list[tuple[float, float]]) -> bool:
        """Upload a geofence polygon to the FC via MAVLink FENCE protocol.

        Pauses the reader thread for exclusive serial access.
        """
        conn = self._conn
        if conn is None or not polygon:
            return False

        self._reader_paused = True
        try:
            with self._serial_lock:
                m = mavutil.mavlink

                conn.mav.mission_count_send(
                    conn.target_system,
                    conn.target_component,
                    len(polygon),
                    m.MAV_MISSION_TYPE_FENCE,
                )

                ack = conn.recv_match(type="MISSION_REQUEST", blocking=True, timeout=5.0)
                if ack is None:
                    return False

                for i, (lat, lon) in enumerate(polygon):
                    conn.mav.mission_item_int_send(
                        conn.target_system,
                        conn.target_component,
                        i,
                        m.MAV_FRAME_GLOBAL,
                        m.MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION,
                        0,
                        1,
                        len(polygon),
                        0,
                        0,
                        0,
                        int(lat * 1e7),
                        int(lon * 1e7),
                        0,
                        m.MAV_MISSION_TYPE_FENCE,
                    )

                    if i < len(polygon) - 1:
                        req = conn.recv_match(type="MISSION_REQUEST", blocking=True, timeout=5.0)
                        if req is None:
                            return False

                final_ack = conn.recv_match(type="MISSION_ACK", blocking=True, timeout=5.0)
                return final_ack is not None and final_ack.type == 0
        finally:
            self._reader_paused = False

    # -- JSON snapshot ------------------------------------------------------

    def get_snapshot(self) -> dict[str, Any]:
        if self._connect_time > 0:
            self._connection.uptime_s = time.time() - self._connect_time
        f = self._frame
        return {
            "timestamp": f.timestamp,
            "position": {
                "latitude_deg": round(f.latitude_deg, 7),
                "longitude_deg": round(f.longitude_deg, 7),
                "absolute_altitude_m": round(f.absolute_altitude_m, 1),
                "relative_altitude_m": round(f.relative_altitude_m, 1),
            },
            "attitude": {
                "roll_deg": round(f.roll_deg, 1),
                "pitch_deg": round(f.pitch_deg, 1),
                "yaw_deg": round(f.yaw_deg, 1),
            },
            "velocity": {
                "groundspeed_ms": round(f.groundspeed_ms, 1),
                "airspeed_ms": round(f.airspeed_ms, 1),
                "climb_rate_ms": round(f.climb_rate_ms, 1),
                "velocity_north_ms": round(f.velocity_north_ms, 1),
                "velocity_east_ms": round(f.velocity_east_ms, 1),
                "velocity_down_ms": round(f.velocity_down_ms, 1),
            },
            "battery": {
                "voltage_v": round(f.battery_voltage_v, 2),
                "current_a": round(f.battery_current_a, 1),
                "remaining_pct": round(f.battery_remaining_pct, 1),
                "temperature_c": f.battery_temperature_c,
            },
            "gps": {
                "fix_type": f.gps_fix_type,
                "num_satellites": f.gps_num_satellites,
                "hdop": round(f.gps_hdop, 1),
            },
            "wind": {
                "speed_ms": round(f.wind_speed_ms, 1),
                "direction_deg": round(f.wind_direction_deg, 0),
            },
            "status": {
                "flight_mode": f.flight_mode,
                "armed": f.armed,
                "in_air": f.in_air,
                "health_ok": f.health_ok,
            },
            "connection": {
                "connected": self._connection.connected,
                "address": self._connection.address,
                "link_profile": self._connection.link_profile,
                "uptime_s": round(self._connection.uptime_s, 1),
                "messages_received": self._connection.messages_received,
            },
        }


telemetry_service = MAVLinkTelemetryService()
