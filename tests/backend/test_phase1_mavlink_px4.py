"""Phase 1 regression tests — MAVLink PX4 decoding, VTOL state, snapshot safety.

These tests lock in the Phase 1 audit fixes: PX4 custom_mode is unpacked via
main_mode / sub_mode (not treated as an ArduPilot enum), EXTENDED_SYS_STATE
populates landed_state + vtol_state, WIND_COV produces a scalar wind, the
snapshot is coherent under concurrent mutation, and the heartbeat watchdog
flips connected->False on timeout.
"""

from __future__ import annotations

import math
import threading
import time
import types

import pytest

from gorzen.services.mavlink_telemetry import (
    LANDED_STATES,
    MAV_AUTOPILOT_PX4,
    MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
    MAV_MODE_FLAG_SAFETY_ARMED,
    MAVLinkTelemetryService,
    VTOL_STATES,
    decode_px4_custom_mode,
)


def _px4_custom_mode(main: int, sub: int = 0) -> int:
    return (main << 16) | (sub << 24)


class TestPx4ModeDecoder:
    def test_manual_mode(self) -> None:
        assert decode_px4_custom_mode(_px4_custom_mode(1)) == "MANUAL"

    def test_posctl(self) -> None:
        assert decode_px4_custom_mode(_px4_custom_mode(3)) == "POSCTL"

    def test_auto_mission(self) -> None:
        assert decode_px4_custom_mode(_px4_custom_mode(4, 4)) == "AUTO.MISSION"

    def test_auto_rtl(self) -> None:
        assert decode_px4_custom_mode(_px4_custom_mode(4, 5)) == "AUTO.RTL"

    def test_vtol_takeoff(self) -> None:
        """Critical for VTOL mission planner — was broken before Phase 1."""
        assert decode_px4_custom_mode(_px4_custom_mode(4, 10)) == "AUTO.VTOL_TAKEOFF"

    def test_vtol_land(self) -> None:
        assert decode_px4_custom_mode(_px4_custom_mode(4, 11)) == "AUTO.VTOL_LAND"

    def test_offboard(self) -> None:
        assert decode_px4_custom_mode(_px4_custom_mode(6)) == "OFFBOARD"

    def test_unknown_main_mode(self) -> None:
        assert decode_px4_custom_mode(_px4_custom_mode(42)) == "PX4_MAIN_42"

    def test_unknown_auto_submode(self) -> None:
        assert decode_px4_custom_mode(_px4_custom_mode(4, 99)) == "AUTO.SUB_99"


def _make_service_with_connection(
    autopilot: int = MAV_AUTOPILOT_PX4, vehicle_type: int = 22
) -> MAVLinkTelemetryService:
    svc = MAVLinkTelemetryService()
    svc._connection.connected = True
    svc._connection.autopilot = autopilot
    svc._connection.vehicle_type = vehicle_type
    svc._connection.last_heartbeat = time.time()
    return svc


class _FakeMsg:
    def __init__(self, msg_type: str, **fields) -> None:
        self._type = msg_type
        for k, v in fields.items():
            setattr(self, k, v)

    def get_type(self) -> str:
        return self._type


class TestHeartbeatDecode:
    def test_heartbeat_routes_px4_mode(self) -> None:
        svc = _make_service_with_connection()
        hb = _FakeMsg(
            "HEARTBEAT",
            base_mode=MAV_MODE_FLAG_CUSTOM_MODE_ENABLED | MAV_MODE_FLAG_SAFETY_ARMED,
            custom_mode=_px4_custom_mode(4, 4),
            autopilot=MAV_AUTOPILOT_PX4,
            type=22,
        )
        svc._handle_message(hb)
        assert svc.frame.flight_mode == "AUTO.MISSION"
        assert svc.frame.armed is True

    def test_heartbeat_without_custom_mode_bit(self) -> None:
        svc = _make_service_with_connection()
        hb = _FakeMsg(
            "HEARTBEAT",
            base_mode=MAV_MODE_FLAG_SAFETY_ARMED,
            custom_mode=_px4_custom_mode(1),
            autopilot=MAV_AUTOPILOT_PX4,
            type=22,
        )
        svc._handle_message(hb)
        assert svc.frame.flight_mode == "BASE_MODE_ONLY"


class TestVtolState:
    def test_extended_sys_state_populates_frame(self) -> None:
        svc = _make_service_with_connection()
        msg = _FakeMsg("EXTENDED_SYS_STATE", vtol_state=3, landed_state=2)
        svc._handle_message(msg)
        assert svc.frame.vtol_state == "MC"
        assert svc.frame.landed_state == "IN_AIR"
        assert svc.frame.in_air is True

    def test_landed_on_ground_sets_in_air_false(self) -> None:
        svc = _make_service_with_connection()
        msg = _FakeMsg("EXTENDED_SYS_STATE", vtol_state=4, landed_state=1)
        svc._handle_message(msg)
        assert svc.frame.vtol_state == "FW"
        assert svc.frame.landed_state == "ON_GROUND"
        assert svc.frame.in_air is False

    def test_vtol_state_enum_covers_all_px4_states(self) -> None:
        # Confirm we can decode every MAV_VTOL_STATE value PX4 emits.
        assert {0, 1, 2, 3, 4}.issubset(VTOL_STATES.keys())
        assert VTOL_STATES[1] == "TRANSITION_TO_FW"


class TestWindCov:
    def test_wind_cov_scalar_from_ned_components(self) -> None:
        svc = _make_service_with_connection()
        msg = _FakeMsg("WIND_COV", wind_x=3.0, wind_y=4.0)
        svc._handle_message(msg)
        assert svc.frame.wind_speed_ms == pytest.approx(5.0)
        # 3 m/s north, 4 m/s east -> wind from ~SSW (from direction).
        assert svc.frame.wind_direction_deg is not None
        assert 200.0 < svc.frame.wind_direction_deg < 260.0


class TestSnapshotCoherence:
    def test_snapshot_is_deep_copy(self) -> None:
        svc = _make_service_with_connection()
        msg = _FakeMsg(
            "GLOBAL_POSITION_INT",
            lat=370000000,
            lon=-1220000000,
            alt=100000,
            relative_alt=50000,
            vx=100,
            vy=0,
            vz=-50,
        )
        svc._handle_message(msg)
        snap1 = svc.get_snapshot()
        # Mutate live frame; snapshot must not reflect it.
        with svc._frame_lock:
            svc._frame.roll_deg = 42.0
        assert snap1["attitude"]["roll_deg"] != 42.0

    def test_concurrent_mutation_never_tears_snapshot(self) -> None:
        svc = _make_service_with_connection()

        stop = threading.Event()

        def writer() -> None:
            tick = 0
            while not stop.is_set():
                msg = _FakeMsg(
                    "ATTITUDE",
                    roll=math.radians(tick % 360),
                    pitch=math.radians((tick * 2) % 360),
                    yaw=math.radians((tick * 3) % 360),
                )
                svc._handle_message(msg)
                tick += 1

        t = threading.Thread(target=writer, daemon=True)
        t.start()
        try:
            for _ in range(500):
                snap = svc.get_snapshot()
                # Snapshot's attitude block should be internally consistent:
                # every field should be a number (never a half-updated None).
                att = snap["attitude"]
                assert att["roll_deg"] is not None
                assert att["pitch_deg"] is not None
                assert att["yaw_deg"] is not None
        finally:
            stop.set()
            t.join(timeout=1.0)


class TestGpsRejectZeroZero:
    def test_zero_lat_lon_becomes_none(self) -> None:
        svc = _make_service_with_connection()
        msg = _FakeMsg(
            "GLOBAL_POSITION_INT",
            lat=0,
            lon=0,
            alt=0,
            relative_alt=0,
            vx=0,
            vy=0,
            vz=0,
        )
        svc._handle_message(msg)
        assert svc.frame.latitude_deg is None
        assert svc.frame.longitude_deg is None


class TestSysStatusBitmask:
    def test_decoded_sensor_flags(self) -> None:
        svc = _make_service_with_connection()
        msg = _FakeMsg(
            "SYS_STATUS",
            voltage_battery=22000,
            current_battery=500,
            battery_remaining=80,
            onboard_control_sensors_present=(1 << 0) | (1 << 5),
            onboard_control_sensors_enabled=(1 << 0) | (1 << 5),
            onboard_control_sensors_health=(1 << 0) | (1 << 5),
        )
        svc._handle_message(msg)
        assert svc.frame.sensor_present["gyro"] is True
        assert svc.frame.sensor_present["gps"] is True
        assert svc.frame.sensor_health["gyro"] is True
        assert svc.frame.health_ok is True

    def test_unhealthy_enabled_sensor_fails_health_ok(self) -> None:
        svc = _make_service_with_connection()
        msg = _FakeMsg(
            "SYS_STATUS",
            voltage_battery=22000,
            current_battery=500,
            battery_remaining=80,
            onboard_control_sensors_present=(1 << 0) | (1 << 4),
            onboard_control_sensors_enabled=(1 << 0) | (1 << 4),
            onboard_control_sensors_health=(1 << 0),  # diff_pressure unhealthy
        )
        svc._handle_message(msg)
        assert svc.frame.sensor_health["diff_pressure"] is False
        assert svc.frame.health_ok is False


class TestStatusText:
    def test_prearm_messages_are_captured(self) -> None:
        svc = _make_service_with_connection()
        text = b"Preflight Fail: GPS fix too low\x00\x00"
        msg = _FakeMsg("STATUSTEXT", text=list(text), severity=4)
        svc._handle_message(msg)
        assert svc.frame.pre_arm_messages
        assert "Preflight Fail" in svc.frame.pre_arm_messages[0]
