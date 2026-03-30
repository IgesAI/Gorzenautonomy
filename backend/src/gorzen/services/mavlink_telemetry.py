"""MAVLink telemetry service using pymavlink.

Manages connections to ArduPilot/PX4 drones via pymavlink (the same library
Mission Planner uses).  Uses REQUEST_DATA_STREAM to configure ArduPilot
telemetry rates — the only method older ArduPilot firmware supports.

The blocking serial recv loop runs in a dedicated OS thread so it never
contends with the asyncio event loop.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import signal
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

ARDUPILOT_COPTER_MODES: dict[int, str] = {
    0: "STABILIZE", 1: "ACRO", 2: "ALT_HOLD", 3: "AUTO", 4: "GUIDED",
    5: "LOITER", 6: "RTL", 7: "CIRCLE", 8: "POSITION", 9: "LAND",
    10: "OF_LOITER", 11: "DRIFT", 13: "SPORT", 14: "FLIP", 15: "AUTOTUNE",
    16: "POSHOLD", 17: "BRAKE", 18: "THROW", 19: "AVOID_ADSB",
    20: "GUIDED_NOGPS", 21: "SMART_RTL", 22: "FLOWHOLD", 23: "FOLLOW",
    24: "ZIGZAG", 25: "SYSTEMID", 26: "AUTOROTATE", 27: "AUTO_RTL",
}

ARDUPILOT_PLANE_MODES: dict[int, str] = {
    0: "MANUAL", 1: "CIRCLE", 2: "STABILIZE", 3: "TRAINING", 4: "ACRO",
    5: "FLY_BY_WIRE_A", 6: "FLY_BY_WIRE_B", 7: "CRUISE", 8: "AUTOTUNE",
    10: "AUTO", 11: "RTL", 12: "LOITER", 13: "TAKEOFF", 14: "AVOID_ADSB",
    15: "GUIDED", 17: "QSTABILIZE", 18: "QHOVER", 19: "QLOITER",
    20: "QLAND", 21: "QRTL", 22: "QAUTOTUNE", 23: "QACRO", 24: "THERMAL",
    25: "LOITER_ALT_QLAND",
}

GPS_FIX_TYPES: dict[int, str] = {
    0: "NO_GPS", 1: "NO_FIX", 2: "2D_FIX", 3: "3D_FIX",
    4: "DGPS", 5: "RTK_FLOAT", 6: "RTK_FIXED",
}

MAV_MODE_FLAG_SAFETY_ARMED = 128


@dataclass
class TelemetryFrame:
    """Single snapshot of all subscribed telemetry channels."""

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
    """Connection info and health."""

    connected: bool = False
    system_id: int = 0
    address: str = ""
    uptime_s: float = 0.0
    last_heartbeat: float = 0.0
    messages_received: int = 0


def _parse_address(address: str) -> tuple[str, int]:
    """Convert our address format to pymavlink device + baud."""
    if address.startswith("serial://"):
        rest = address[len("serial://"):]
        if ":" in rest:
            parts = rest.rsplit(":", 1)
            return parts[0], int(parts[1])
        return rest, 57600
    if address.startswith("udp://"):
        rest = address[len("udp://"):]
        return f"udpin:{rest or '0.0.0.0:14540'}", 115200
    if address.startswith("tcp://"):
        rest = address[len("tcp://"):]
        return f"tcp:{rest}", 115200
    if address.upper().startswith("COM") or address.startswith("/dev/"):
        if ":" in address:
            parts = address.rsplit(":", 1)
            return parts[0], int(parts[1])
        return address, 57600
    return address, 57600


def _kill_mavsdk_servers() -> None:
    """Force-kill any lingering mavsdk_server processes to release serial ports."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", "mavsdk_server_bin.exe"],
                           capture_output=True, timeout=5)
            subprocess.run(["taskkill", "/F", "/IM", "mavsdk_server.exe"],
                           capture_output=True, timeout=5)
        else:
            subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True, timeout=5)
    except Exception:
        pass


class MAVLinkTelemetryService:
    """Async service that connects to a drone and streams telemetry via pymavlink."""

    def __init__(self) -> None:
        self._conn: Any = None
        self._frame = TelemetryFrame()
        self._connection = ConnectionState()
        self._subscribers: list[asyncio.Queue[TelemetryFrame]] = []
        self._broadcast_task: asyncio.Task[None] | None = None
        self._recv_thread: threading.Thread | None = None
        self._running = False
        self._connect_time = 0.0
        self._vehicle_type: int = 2

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

    async def connect(self, address: str = "udp://:14540") -> bool:
        if not PYMAVLINK_AVAILABLE:
            logger.warning("pymavlink not installed — running in simulation mode")
            self._connection = ConnectionState(connected=False, address=address)
            return False

        try:
            await self.disconnect()
            _kill_mavsdk_servers()

            device, baud = _parse_address(address)
            logger.info("Connecting to %s @ %d baud", device, baud)

            loop = asyncio.get_running_loop()
            self._conn = await loop.run_in_executor(
                None,
                lambda: mavutil.mavlink_connection(device, baud=baud, source_system=255),
            )

            logger.info("Waiting for heartbeat …")
            heartbeat = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self._conn.wait_heartbeat(timeout=30)),
                timeout=35.0,
            )
            if heartbeat is None:
                logger.error("No heartbeat received")
                self._conn.close()
                self._conn = None
                self._connection = ConnectionState(connected=False, address=address)
                return False

            self._vehicle_type = heartbeat.type
            self._connection = ConnectionState(
                connected=True,
                system_id=self._conn.target_system,
                address=address,
                last_heartbeat=time.time(),
            )
            self._connect_time = time.time()

            # REQUEST_DATA_STREAM — the only method ArduPilot reliably supports.
            # This is exactly what Mission Planner sends.
            for stream_id, rate in [
                (mavutil.mavlink.MAV_DATA_STREAM_RAW_SENSORS, 2),
                (mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS, 2),
                (mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS, 2),
                (mavutil.mavlink.MAV_DATA_STREAM_POSITION, 10),
                (mavutil.mavlink.MAV_DATA_STREAM_EXTRA1, 10),
                (mavutil.mavlink.MAV_DATA_STREAM_EXTRA2, 10),
                (mavutil.mavlink.MAV_DATA_STREAM_EXTRA3, 2),
            ]:
                self._conn.mav.request_data_stream_send(
                    self._conn.target_system,
                    self._conn.target_component,
                    stream_id,
                    rate,
                    1,
                )
            logger.info("Sent REQUEST_DATA_STREAM for all groups")

            self._running = True
            self._recv_thread = threading.Thread(
                target=self._recv_thread_fn, name="mavlink-recv", daemon=True,
            )
            self._recv_thread.start()
            self._broadcast_task = asyncio.create_task(self._broadcast_loop())

            logger.info(
                "Connected to system %d at %s (vehicle type %d)",
                self._conn.target_system, address, self._vehicle_type,
            )
            return True

        except Exception as e:
            logger.error("Connection failed: %s", e)
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
            self._connection = ConnectionState(connected=False, address=address)
            return False

    async def disconnect(self) -> None:
        if not self._running and self._conn is None:
            return
        logger.info("Disconnecting telemetry …")
        self._running = False

        if self._recv_thread is not None and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=3.0)
            self._recv_thread = None

        if self._broadcast_task is not None:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
            self._broadcast_task = None

        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

        self._connection.connected = False
        self._frame = TelemetryFrame()
        logger.info("Telemetry disconnected cleanly")

    def subscribe(self) -> asyncio.Queue[TelemetryFrame]:
        q: asyncio.Queue[TelemetryFrame] = asyncio.Queue(maxsize=50)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[TelemetryFrame]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def stream(self) -> AsyncIterator[TelemetryFrame]:
        q = self.subscribe()
        try:
            while self._running:
                frame = await q.get()
                yield frame
        finally:
            self.unsubscribe(q)

    def _decode_flight_mode(self, base_mode: int, custom_mode: int) -> str:
        if self._vehicle_type in (1, 2, 3, 4, 13, 14, 15, 29):
            return ARDUPILOT_COPTER_MODES.get(custom_mode, f"MODE_{custom_mode}")
        if self._vehicle_type in (0, 5, 6, 7, 8, 9, 10, 11, 12, 16, 19, 20, 21, 22):
            return ARDUPILOT_PLANE_MODES.get(custom_mode, f"MODE_{custom_mode}")
        return f"MODE_{custom_mode}"

    def _handle_message(self, msg: Any) -> None:
        msg_type = msg.get_type()
        now = time.time()

        if msg_type == "HEARTBEAT":
            self._frame.armed = bool(msg.base_mode & MAV_MODE_FLAG_SAFETY_ARMED)
            self._frame.flight_mode = self._decode_flight_mode(msg.base_mode, msg.custom_mode)
            self._connection.last_heartbeat = now
            self._connection.messages_received += 1

        elif msg_type == "GLOBAL_POSITION_INT":
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

        elif msg_type == "ATTITUDE":
            self._frame.roll_deg = math.degrees(msg.roll)
            self._frame.pitch_deg = math.degrees(msg.pitch)
            self._frame.yaw_deg = math.degrees(msg.yaw) % 360
            self._frame.timestamp = now
            self._connection.messages_received += 1

        elif msg_type == "VFR_HUD":
            self._frame.airspeed_ms = msg.airspeed
            self._frame.groundspeed_ms = msg.groundspeed
            self._frame.climb_rate_ms = msg.climb
            self._connection.messages_received += 1

        elif msg_type == "SYS_STATUS":
            self._frame.battery_voltage_v = msg.voltage_battery / 1000.0
            if msg.current_battery >= 0:
                self._frame.battery_current_a = msg.current_battery / 100.0
            if msg.battery_remaining >= 0:
                self._frame.battery_remaining_pct = float(msg.battery_remaining)
            self._frame.health_ok = (msg.onboard_control_sensors_health & 0x01) != 0
            self._connection.messages_received += 1

        elif msg_type == "GPS_RAW_INT":
            fix = msg.fix_type
            self._frame.gps_fix_type = GPS_FIX_TYPES.get(fix, f"FIX_{fix}")
            self._frame.gps_num_satellites = msg.satellites_visible
            if msg.eph != 65535:
                self._frame.gps_hdop = msg.eph / 100.0
            self._connection.messages_received += 1

        elif msg_type == "WIND":
            self._frame.wind_direction_deg = msg.direction
            self._frame.wind_speed_ms = msg.speed
            self._connection.messages_received += 1

        elif msg_type == "RC_CHANNELS":
            if msg.rssi != 255:
                self._frame.rc_signal_strength_pct = (msg.rssi / 254.0) * 100
            self._connection.messages_received += 1

        elif msg_type == "BATTERY_STATUS":
            if hasattr(msg, "temperature") and msg.temperature != 32767:
                self._frame.battery_temperature_c = msg.temperature / 100.0
            self._connection.messages_received += 1

    def _recv_thread_fn(self) -> None:
        """Tight blocking recv loop in a dedicated OS thread."""
        logger.info("Recv thread started")
        while self._running:
            try:
                conn = self._conn
                if conn is None:
                    break
                msg = conn.recv_match(blocking=True, timeout=0.5)
                if msg is not None:
                    self._handle_message(msg)
            except Exception as e:
                if self._running:
                    logger.warning("Recv thread error: %s", e)
                break
        logger.info("Recv thread exited")

    async def _broadcast_loop(self) -> None:
        """Push current frame to subscribers at ~10 Hz."""
        try:
            while self._running:
                self._connection.uptime_s = time.time() - self._connect_time
                for q in self._subscribers:
                    try:
                        q.put_nowait(TelemetryFrame(**self._frame.__dict__))
                    except asyncio.QueueFull:
                        pass
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return

    def get_snapshot(self) -> dict[str, Any]:
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
                "uptime_s": round(self._connection.uptime_s, 1),
                "messages_received": self._connection.messages_received,
            },
        }


telemetry_service = MAVLinkTelemetryService()
