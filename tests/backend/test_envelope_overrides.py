"""Envelope param_overrides: ignored keys reported on EnvelopeResponse."""

from __future__ import annotations

from gorzen.api.routers.envelope import _apply_param_overrides
from gorzen.schemas.twin_graph import VehicleTwin


def test_apply_param_overrides_reports_unknown_subsystem() -> None:
    twin = VehicleTwin()
    ignored = _apply_param_overrides(
        twin,
        {"not_a_real_subsystem": {"foo": 1.0}},
    )
    assert any("not_a_real_subsystem.foo" == x for x in ignored)


def test_apply_param_overrides_reports_unknown_mission_field() -> None:
    twin = VehicleTwin()
    ignored = _apply_param_overrides(
        twin,
        {"mission_profile": {"totally_unknown_field_xyz": 1.0}},
    )
    assert "mission_profile.totally_unknown_field_xyz" in ignored
