"""MAVLink / MAVSDK telemetry service.

Manages connections to PX4 drones (real or SITL) via MAVSDK-Python.
Streams live telemetry and exposes async iterators for WebSocket relay.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

# MAVSDK is optional at import time — degrade gracefully if not installed
try:
    from mavsdk import System
    from mavsdk.telemetry import FlightMode, StatusText

    MAVSDK_AVAILABLE = True
except ImportError:
    MAVSDK_AVAILABLE = False
    System = None  # type: ignore


@dataclass
class TelemetryFrame:
    """Single snapshot of all subscribed telemetry channels."""

    timestamp: float = 0.0
    # Position
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    absolute_altitude_m: float = 0.0
    relative_altitude_m: float = 0.0
    # Attitude
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    # Velocity
    velocity_north_ms: float = 0.0
    velocity_east_ms: float = 0.0
    velocity_down_ms: float = 0.0
    groundspeed_ms: float = 0.0
    airspeed_ms: float = 0.0
    climb_rate_ms: float = 0.0
    # Battery
    battery_voltage_v: float = 0.0
    battery_current_a: float = 0.0
    battery_remaining_pct: float = 0.0
    battery_temperature_c: float | None = None
    # GPS
    gps_fix_type: str = "NO_FIX"
    gps_num_satellites: int = 0
    gps_hdop: float = 99.0
    # Wind estimate (PX4 EKF)
    wind_speed_ms: float = 0.0
    wind_direction_deg: float = 0.0
    # Flight status
    flight_mode: str = "UNKNOWN"
    armed: bool = False
    in_air: bool = False
    health_ok: bool = False
    # Actuators
    actuator_outputs: list[float] = field(default_factory=list)
    # RC
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


class MAVLinkTelemetryService:
    """Async service that connects to a PX4 drone and streams telemetry."""

    def __init__(self) -> None:
        self._system: Any = None
        self._frame = TelemetryFrame()
        self._connection = ConnectionState()
        self._subscribers: list[asyncio.Queue[TelemetryFrame]] = []
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._connect_time = 0.0

    @property
    def frame(self) -> TelemetryFrame:
        return self._frame

    @property
    def connection(self) -> ConnectionState:
        return self._connection

    @property
    def is_connected(self) -> bool:
        return self._connection.connected

    async def connect(self, address: str = "udp://:14540") -> bool:
        """Connect to a PX4 drone or SITL instance.

        Common addresses:
        - udp://:14540  — PX4 SITL default
        - udp://:14550  — QGroundControl default
        - serial:///dev/ttyUSB0:57600  — serial telemetry radio
        - serial://COM3:57600  — Windows serial
        """
        if not MAVSDK_AVAILABLE:
            logger.warning("MAVSDK not installed — running in simulation mode")
            self._connection = ConnectionState(
                connected=False, address=address,
            )
            return False

        try:
            self._system = System()
            await self._system.connect(system_address=address)

            # Wait for connection with timeout
            connected = False
            async for state in self._system.core.connection_state():
                if state.is_connected:
                    connected = True
                    break

            if not connected:
                return False

            self._connect_time = time.time()
            self._connection = ConnectionState(
                connected=True,
                address=address,
                last_heartbeat=time.time(),
            )

            # Start subscription tasks
            self._running = True
            self._tasks = [
                asyncio.create_task(self._subscribe_position()),
                asyncio.create_task(self._subscribe_attitude()),
                asyncio.create_task(self._subscribe_battery()),
                asyncio.create_task(self._subscribe_gps()),
                asyncio.create_task(self._subscribe_flight_mode()),
                asyncio.create_task(self._subscribe_velocity()),
                asyncio.create_task(self._subscribe_in_air()),
                asyncio.create_task(self._subscribe_armed()),
                asyncio.create_task(self._subscribe_health()),
                asyncio.create_task(self._broadcast_loop()),
            ]
            logger.info(f"Connected to drone at {address}")
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._connection = ConnectionState(connected=False, address=address)
            return False

    async def disconnect(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        self._connection.connected = False

    def subscribe(self) -> asyncio.Queue[TelemetryFrame]:
        """Get a queue that receives telemetry frames at ~10 Hz."""
        q: asyncio.Queue[TelemetryFrame] = asyncio.Queue(maxsize=50)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[TelemetryFrame]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def stream(self) -> AsyncIterator[TelemetryFrame]:
        """Async generator that yields telemetry frames."""
        q = self.subscribe()
        try:
            while self._running:
                frame = await q.get()
                yield frame
        finally:
            self.unsubscribe(q)

    # --- Internal subscription tasks ---

    async def _subscribe_position(self) -> None:
        async for pos in self._system.telemetry.position():
            self._frame.latitude_deg = pos.latitude_deg
            self._frame.longitude_deg = pos.longitude_deg
            self._frame.absolute_altitude_m = pos.absolute_altitude_m
            self._frame.relative_altitude_m = pos.relative_altitude_m
            self._frame.timestamp = time.time()
            self._connection.messages_received += 1

    async def _subscribe_attitude(self) -> None:
        async for att in self._system.telemetry.attitude_euler():
            self._frame.roll_deg = att.roll_deg
            self._frame.pitch_deg = att.pitch_deg
            self._frame.yaw_deg = att.yaw_deg

    async def _subscribe_battery(self) -> None:
        async for batt in self._system.telemetry.battery():
            self._frame.battery_voltage_v = batt.voltage_v
            self._frame.battery_current_a = batt.current_battery_a
            self._frame.battery_remaining_pct = batt.remaining_percent * 100

    async def _subscribe_gps(self) -> None:
        async for gps in self._system.telemetry.gps_info():
            self._frame.gps_fix_type = str(gps.fix_type)
            self._frame.gps_num_satellites = gps.num_satellites

    async def _subscribe_velocity(self) -> None:
        async for vel in self._system.telemetry.velocity_ned():
            self._frame.velocity_north_ms = vel.north_m_s
            self._frame.velocity_east_ms = vel.east_m_s
            self._frame.velocity_down_ms = vel.down_m_s
            self._frame.groundspeed_ms = (vel.north_m_s**2 + vel.east_m_s**2) ** 0.5
            self._frame.climb_rate_ms = -vel.down_m_s

    async def _subscribe_flight_mode(self) -> None:
        async for mode in self._system.telemetry.flight_mode():
            self._frame.flight_mode = str(mode)

    async def _subscribe_in_air(self) -> None:
        async for in_air in self._system.telemetry.in_air():
            self._frame.in_air = in_air

    async def _subscribe_armed(self) -> None:
        async for armed in self._system.telemetry.armed():
            self._frame.armed = armed

    async def _subscribe_health(self) -> None:
        async for health in self._system.telemetry.health():
            self._frame.health_ok = health.is_global_position_ok

    async def _broadcast_loop(self) -> None:
        """Broadcast current frame to all subscribers at ~10 Hz."""
        while self._running:
            self._connection.uptime_s = time.time() - self._connect_time
            self._connection.last_heartbeat = time.time()
            for q in self._subscribers:
                try:
                    q.put_nowait(TelemetryFrame(**self._frame.__dict__))
                except asyncio.QueueFull:
                    pass
            await asyncio.sleep(0.1)

    def get_snapshot(self) -> dict[str, Any]:
        """Get current telemetry as a JSON-serializable dict."""
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


# Singleton for app-wide access
telemetry_service = MAVLinkTelemetryService()
