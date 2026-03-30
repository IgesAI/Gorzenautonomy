"""gorzen_bridge: ROS 2 node that subscribes to PX4 telemetry via uXRCE-DDS
and forwards aggregated TelemetryFrames to the Gorzen planner REST API.

This is the Phase 1 deliverable — a second telemetry path alongside the
existing pymavlink service, allowing A/B comparison from the same frontend
WebSocket.

Architecture:
  PX4 ─► uXRCE-DDS Agent ─► ROS 2 DDS ─► this node ─► HTTP POST ─► gorzen-planner
                                               └─► publishes gorzen_msgs/TelemetryFrame
"""

from __future__ import annotations

import math
import threading
from typing import Any

import httpx
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor

from gorzen_bridge.px4_qos import PX4_QOS, GORZEN_RELIABLE_QOS

try:
    from px4_msgs.msg import (
        BatteryStatus,
        SensorGps,
        VehicleAttitude,
        VehicleLocalPosition,
        VehicleGlobalPosition,
        VehicleStatus,
    )
    PX4_MSGS_AVAILABLE = True
except ImportError:
    PX4_MSGS_AVAILABLE = False

from gorzen_msgs.msg import TelemetryFrame


PX4_NAV_STATE_MAP: dict[int, str] = {
    0: "MANUAL", 1: "ALTCTL", 2: "POSCTL", 3: "AUTO_MISSION",
    4: "AUTO_LOITER", 5: "AUTO_RTL", 6: "RC_RECOVERY", 7: "AUTO_RTGS",
    8: "AUTO_LANDENGFAIL", 10: "ACRO", 12: "DESCEND", 13: "TERMINATION",
    14: "OFFBOARD", 15: "STAB", 17: "AUTO_TAKEOFF", 18: "AUTO_LAND",
    19: "AUTO_FOLLOW_TARGET", 20: "AUTO_PRECLAND", 21: "ORBIT",
    22: "AUTO_VTOL_TAKEOFF",
}

GPS_FIX_MAP: dict[int, int] = {
    0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6,
}


def _quat_to_euler(w: float, x: float, y: float, z: float) -> tuple[float, float, float]:
    """Quaternion → Euler (roll, pitch, yaw) in degrees."""
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.asin(sinp)

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw) % 360


class BridgeNode(Node):
    """Subscribes to PX4 uORB topics via uXRCE-DDS, aggregates into a
    TelemetryFrame, publishes on /gorzen/telemetry/frame, and POSTs to
    the gorzen-planner REST API at a configurable rate."""

    def __init__(self) -> None:
        super().__init__("gorzen_bridge")

        self.declare_parameter("planner_url", "http://localhost:8000")
        self.declare_parameter("forward_rate_hz", 10.0)
        self.declare_parameter("source", "ros2")
        self.declare_parameter("vehicle_ns", "")

        self._planner_url: str = self.get_parameter("planner_url").value  # type: ignore[assignment]
        forward_hz: float = self.get_parameter("forward_rate_hz").value  # type: ignore[assignment]
        self._source: str = self.get_parameter("source").value  # type: ignore[assignment]
        vehicle_ns: str = self.get_parameter("vehicle_ns").value  # type: ignore[assignment]

        ns_prefix = f"/{vehicle_ns}" if vehicle_ns else ""
        self._fmu_prefix = f"{ns_prefix}/fmu/out"

        self._frame = TelemetryFrame()
        self._frame_lock = threading.Lock()

        self._http = httpx.Client(
            base_url=self._planner_url,
            timeout=2.0,
            headers={"Content-Type": "application/json"},
        )
        self._post_errors = 0

        self._pub_frame = self.create_publisher(
            TelemetryFrame,
            "/gorzen/telemetry/frame",
            GORZEN_RELIABLE_QOS,
        )

        if self._source == "ros2" and PX4_MSGS_AVAILABLE:
            self._setup_px4_subscriptions()
        elif self._source == "ros2" and not PX4_MSGS_AVAILABLE:
            self.get_logger().error(
                "px4_msgs not found — install from https://github.com/PX4/px4_msgs. "
                "Falling back to idle."
            )
        else:
            self.get_logger().info(f"Source mode: {self._source} (no PX4 subscriptions)")

        period = 1.0 / max(forward_hz, 0.1)
        self._forward_timer = self.create_timer(period, self._forward_callback)

        self.get_logger().info(
            f"Bridge started — planner={self._planner_url}, "
            f"rate={forward_hz} Hz, source={self._source}, "
            f"fmu_prefix={self._fmu_prefix}"
        )

    def _setup_px4_subscriptions(self) -> None:
        """Subscribe to PX4 uORB topics exposed through uXRCE-DDS."""
        self.create_subscription(
            VehicleGlobalPosition,
            f"{self._fmu_prefix}/vehicle_global_position",
            self._on_global_position,
            PX4_QOS,
        )
        self.create_subscription(
            VehicleLocalPosition,
            f"{self._fmu_prefix}/vehicle_local_position",
            self._on_local_position,
            PX4_QOS,
        )
        self.create_subscription(
            VehicleAttitude,
            f"{self._fmu_prefix}/vehicle_attitude",
            self._on_attitude,
            PX4_QOS,
        )
        self.create_subscription(
            BatteryStatus,
            f"{self._fmu_prefix}/battery_status",
            self._on_battery,
            PX4_QOS,
        )
        self.create_subscription(
            VehicleStatus,
            f"{self._fmu_prefix}/vehicle_status",
            self._on_vehicle_status,
            PX4_QOS,
        )
        self.create_subscription(
            SensorGps,
            f"{self._fmu_prefix}/vehicle_gps_position",
            self._on_gps,
            PX4_QOS,
        )
        self.get_logger().info("PX4 uXRCE-DDS subscriptions active")

    # ── PX4 topic callbacks ──────────────────────────────────────────

    def _on_global_position(self, msg: Any) -> None:
        with self._frame_lock:
            self._frame.latitude_deg = msg.lat
            self._frame.longitude_deg = msg.lon
            self._frame.altitude_amsl_m = float(msg.alt)
            self._frame.altitude_agl_m = float(msg.alt_ellipsoid - msg.alt) if hasattr(msg, "alt_ellipsoid") else 0.0

    def _on_local_position(self, msg: Any) -> None:
        with self._frame_lock:
            self._frame.vn_ms = float(msg.vx)
            self._frame.ve_ms = float(msg.vy)
            self._frame.vd_ms = float(msg.vz)
            self._frame.groundspeed_ms = math.hypot(msg.vx, msg.vy)
            self._frame.climb_rate_ms = float(-msg.vz)
            if hasattr(msg, "dist_bottom_valid") and msg.dist_bottom_valid:
                self._frame.altitude_agl_m = float(msg.dist_bottom)

    def _on_attitude(self, msg: Any) -> None:
        q = msg.q
        roll, pitch, yaw = _quat_to_euler(q[0], q[1], q[2], q[3])
        with self._frame_lock:
            self._frame.roll_deg = roll
            self._frame.pitch_deg = pitch
            self._frame.yaw_deg = yaw

    def _on_battery(self, msg: Any) -> None:
        with self._frame_lock:
            self._frame.battery_voltage_v = float(msg.voltage_v)
            self._frame.battery_current_a = float(abs(msg.current_a))
            remaining = msg.remaining
            self._frame.battery_remaining_pct = float(remaining * 100) if remaining >= 0 else 0.0

    def _on_vehicle_status(self, msg: Any) -> None:
        with self._frame_lock:
            self._frame.armed = bool(msg.arming_state == 2)  # ARMED
            self._frame.flight_mode = PX4_NAV_STATE_MAP.get(msg.nav_state, f"NAV_{msg.nav_state}")
            self._frame.in_air = not msg.vehicle_land_detected if hasattr(msg, "vehicle_land_detected") else self._frame.armed
            self._frame.health_ok = not msg.failsafe

    def _on_gps(self, msg: Any) -> None:
        with self._frame_lock:
            self._frame.gps_fix = GPS_FIX_MAP.get(msg.fix_type, 0)
            self._frame.satellites = msg.satellites_used

    # ── Forward timer ────────────────────────────────────────────────

    def _forward_callback(self) -> None:
        """Publish TelemetryFrame and POST snapshot to planner."""
        with self._frame_lock:
            frame = TelemetryFrame()
            frame.header.stamp = self.get_clock().now().to_msg()
            frame.latitude_deg = self._frame.latitude_deg
            frame.longitude_deg = self._frame.longitude_deg
            frame.altitude_amsl_m = self._frame.altitude_amsl_m
            frame.altitude_agl_m = self._frame.altitude_agl_m
            frame.roll_deg = self._frame.roll_deg
            frame.pitch_deg = self._frame.pitch_deg
            frame.yaw_deg = self._frame.yaw_deg
            frame.vn_ms = self._frame.vn_ms
            frame.ve_ms = self._frame.ve_ms
            frame.vd_ms = self._frame.vd_ms
            frame.groundspeed_ms = self._frame.groundspeed_ms
            frame.airspeed_ms = self._frame.airspeed_ms
            frame.climb_rate_ms = self._frame.climb_rate_ms
            frame.battery_voltage_v = self._frame.battery_voltage_v
            frame.battery_current_a = self._frame.battery_current_a
            frame.battery_remaining_pct = self._frame.battery_remaining_pct
            frame.gps_fix = self._frame.gps_fix
            frame.satellites = self._frame.satellites
            frame.armed = self._frame.armed
            frame.flight_mode = self._frame.flight_mode
            frame.in_air = self._frame.in_air
            frame.health_ok = self._frame.health_ok
            frame.wind_speed_ms = self._frame.wind_speed_ms
            frame.wind_direction_deg = self._frame.wind_direction_deg

        self._pub_frame.publish(frame)
        self._post_to_planner(frame)

    def _post_to_planner(self, frame: TelemetryFrame) -> None:
        """POST aggregated frame to gorzen-planner telemetry ingestion endpoint."""
        payload = {
            "source": "ros2_bridge",
            "timestamp": frame.header.stamp.sec + frame.header.stamp.nanosec * 1e-9,
            "position": {
                "latitude_deg": round(frame.latitude_deg, 7),
                "longitude_deg": round(frame.longitude_deg, 7),
                "absolute_altitude_m": round(frame.altitude_amsl_m, 1),
                "relative_altitude_m": round(frame.altitude_agl_m, 1),
            },
            "attitude": {
                "roll_deg": round(frame.roll_deg, 1),
                "pitch_deg": round(frame.pitch_deg, 1),
                "yaw_deg": round(frame.yaw_deg, 1),
            },
            "velocity": {
                "groundspeed_ms": round(frame.groundspeed_ms, 1),
                "airspeed_ms": round(frame.airspeed_ms, 1),
                "climb_rate_ms": round(frame.climb_rate_ms, 1),
                "velocity_north_ms": round(frame.vn_ms, 1),
                "velocity_east_ms": round(frame.ve_ms, 1),
                "velocity_down_ms": round(frame.vd_ms, 1),
            },
            "battery": {
                "voltage_v": round(frame.battery_voltage_v, 2),
                "current_a": round(frame.battery_current_a, 1),
                "remaining_pct": round(frame.battery_remaining_pct, 1),
            },
            "gps": {
                "fix_type": frame.gps_fix,
                "num_satellites": frame.satellites,
            },
            "wind": {
                "speed_ms": round(frame.wind_speed_ms, 1),
                "direction_deg": round(frame.wind_direction_deg, 0),
            },
            "status": {
                "flight_mode": frame.flight_mode,
                "armed": frame.armed,
                "in_air": frame.in_air,
                "health_ok": frame.health_ok,
            },
        }
        try:
            resp = self._http.post("/telemetry/ingest", json=payload)
            if resp.status_code >= 400 and self._post_errors < 5:
                self._post_errors += 1
                self.get_logger().warning(
                    f"Planner ingest returned {resp.status_code}: {resp.text[:200]}"
                )
        except httpx.ConnectError:
            if self._post_errors < 3:
                self._post_errors += 1
                self.get_logger().warning(
                    f"Cannot reach planner at {self._planner_url} — "
                    "will keep retrying silently"
                )
        except Exception as e:
            if self._post_errors < 5:
                self._post_errors += 1
                self.get_logger().warning(f"POST error: {e}")

    def destroy_node(self) -> None:
        self._http.close()
        super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = BridgeNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
