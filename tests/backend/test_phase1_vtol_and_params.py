"""Phase 1 regression tests — VTOL mission items and PX4 param round-trip types."""

from __future__ import annotations

import pytest

from gorzen.schemas.mission import MissionPlan, Waypoint, WaypointType
from gorzen.services.mission_export import (
    MAV_CMD_DO_VTOL_TRANSITION,
    MAV_CMD_NAV_VTOL_LAND,
    MAV_CMD_NAV_VTOL_TAKEOFF,
    MAV_VTOL_STATE_FW,
    MAV_VTOL_STATE_MC,
    export_px4_mission,
    export_qgc_plan,
)
from gorzen.services.px4_params import (
    INTEGER_PARAM_TYPES,
    MAV_PARAM_TYPE_INT32,
    MAV_PARAM_TYPE_REAL32,
    ParamTransformError,
    px4_to_twin,
    twin_to_px4,
)


def _vtol_mission() -> MissionPlan:
    wps = [
        Waypoint(
            sequence=0,
            wp_type=WaypointType.VTOL_TAKEOFF,
            latitude_deg=37.0,
            longitude_deg=-122.0,
            altitude_m=50.0,
        ),
        Waypoint(
            sequence=1,
            wp_type=WaypointType.TRANSITION_TO_FW,
            latitude_deg=37.001,
            longitude_deg=-122.001,
            altitude_m=100.0,
        ),
        Waypoint(
            sequence=2,
            wp_type=WaypointType.NAVIGATE,
            latitude_deg=37.01,
            longitude_deg=-122.01,
            altitude_m=120.0,
            speed_ms=22.0,
        ),
        Waypoint(
            sequence=3,
            wp_type=WaypointType.TRANSITION_TO_MC,
            latitude_deg=37.02,
            longitude_deg=-122.02,
            altitude_m=60.0,
        ),
        Waypoint(
            sequence=4,
            wp_type=WaypointType.VTOL_LAND,
            latitude_deg=37.02,
            longitude_deg=-122.02,
            altitude_m=0.0,
        ),
    ]
    return MissionPlan(twin_id="vtol-test", waypoints=wps)


class TestVtolMissionExport:
    def test_px4_mission_emits_vtol_commands(self) -> None:
        plan = _vtol_mission()
        items = export_px4_mission(plan)
        commands = [i["command"] for i in items]
        assert commands[0] == MAV_CMD_NAV_VTOL_TAKEOFF
        assert commands[1] == MAV_CMD_DO_VTOL_TRANSITION
        assert commands[3] == MAV_CMD_DO_VTOL_TRANSITION
        assert commands[4] == MAV_CMD_NAV_VTOL_LAND

    def test_transition_param1_targets_correct_vtol_state(self) -> None:
        plan = _vtol_mission()
        items = export_px4_mission(plan)
        # sequence 1 -> TRANSITION_TO_FW, sequence 3 -> TRANSITION_TO_MC.
        assert int(items[1]["param1"]) == MAV_VTOL_STATE_FW
        assert int(items[3]["param1"]) == MAV_VTOL_STATE_MC

    def test_qgc_plan_has_vtol_items(self) -> None:
        plan = _vtol_mission()
        qgc = export_qgc_plan(plan)
        commands = [i["command"] for i in qgc["mission"]["items"]]
        assert MAV_CMD_NAV_VTOL_TAKEOFF in commands
        assert MAV_CMD_NAV_VTOL_LAND in commands
        assert MAV_CMD_DO_VTOL_TRANSITION in commands


class TestPx4ParamTypes:
    def test_integer_cell_count_typed_as_int32(self) -> None:
        typed = twin_to_px4({"energy": {"cell_count_s": 6.0}})
        assert "BAT1_N_CELLS" in typed
        val, ptype = typed["BAT1_N_CELLS"]
        assert ptype == MAV_PARAM_TYPE_INT32
        assert ptype in INTEGER_PARAM_TYPES
        # Integer params must be rounded, not truncated.
        assert val == 6.0

    def test_float_param_typed_as_real32(self) -> None:
        typed = twin_to_px4({"airframe": {"mass_mtow_kg": 12.5}})
        assert "WEIGHT_GROSS" in typed
        _, ptype = typed["WEIGHT_GROSS"]
        assert ptype == MAV_PARAM_TYPE_REAL32

    def test_round_trip_preserves_value(self) -> None:
        twin = {
            "energy": {
                "cell_count_s": 6.0,
                "capacity_ah": 15.0,
                "nominal_voltage_v": 22.2,
            }
        }
        # Simulate an FC response: (value, type) tuples.
        typed = twin_to_px4(twin)
        fc_shaped = {name: (v, t) for name, (v, t) in typed.items()}
        twin_back = px4_to_twin(fc_shaped)
        assert twin_back["energy"]["cell_count_s"] == pytest.approx(6.0)
        assert twin_back["energy"]["capacity_ah"] == pytest.approx(15.0, rel=1e-3)

    def test_strict_mode_raises_on_bad_transform(self) -> None:
        """Prior version swallowed exceptions silently; we now surface them.

        A malformed parameter that survives the float() coercion but fails the
        safe_eval transform is the path we explicitly guard with
        ``ParamTransformError``. A non-numeric value on a required param fails
        earlier with a plain ``ValueError`` — either way the call raises
        instead of silently dropping the param.
        """
        # cell_count_s coerces to float early, surfaces as ValueError when bad.
        with pytest.raises((ParamTransformError, ValueError)):
            twin_to_px4({"energy": {"cell_count_s": "not-a-number"}}, strict=True)

    def test_non_strict_mode_logs_and_continues(self, caplog: pytest.LogCaptureFixture) -> None:
        """Non-strict mode must never silently drop — it must log a warning."""
        import logging

        caplog.set_level(logging.WARNING, logger="gorzen.services.px4_params")
        # Valid cell_count; inject a bad transform by breaking the mass param.
        typed = twin_to_px4(
            {"energy": {"cell_count_s": 6.0}, "airframe": {"mass_mtow_kg": "bad"}},
            strict=False,
        )
        assert "BAT1_N_CELLS" in typed
        assert "WEIGHT_GROSS" not in typed
        assert any("WEIGHT_GROSS" in rec.message for rec in caplog.records)
