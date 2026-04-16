"""Phase 4 golden-file test: every captured PX4 heartbeat decodes to the
mode QGroundControl would display.

Add new cases by dropping them into ``fixtures/px4_heartbeats.json``. This
protects us against future refactors of the PX4 mode tables / bitfield
layout ("it worked locally" regressions that used to slip by).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gorzen.services.mavlink_telemetry import (
    MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
    MAVLinkTelemetryService,
)


FIXTURE = Path(__file__).parent / "fixtures" / "px4_heartbeats.json"


def _load_cases() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class _FakeMsg:
    def __init__(self, **fields) -> None:
        for k, v in fields.items():
            setattr(self, k, v)

    def get_type(self) -> str:
        return "HEARTBEAT"


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c.get("comment", ""))
def test_px4_mode_matches_golden(case: dict) -> None:
    svc = MAVLinkTelemetryService()
    svc._connection.connected = True
    svc._connection.autopilot = int(case["autopilot"])
    svc._connection.vehicle_type = int(case["vehicle_type"])
    msg = _FakeMsg(
        base_mode=int(case["base_mode"]),
        custom_mode=int(case["custom_mode"]),
        autopilot=int(case["autopilot"]),
        type=int(case["vehicle_type"]),
    )
    svc._handle_message(msg)
    assert svc.frame.flight_mode == case["expected_mode"], (
        f"{case.get('comment', '')}: decoded {svc.frame.flight_mode!r}, "
        f"expected {case['expected_mode']!r}"
    )


def test_all_golden_heartbeats_have_custom_mode_bit_or_are_base_only() -> None:
    """Sanity check on fixture: all PX4 AUTO/MANUAL samples must have
    the ``MAV_MODE_FLAG_CUSTOM_MODE_ENABLED`` bit set, except ones that
    explicitly test the ``BASE_MODE_ONLY`` fallback."""
    for case in _load_cases():
        has_custom = bool(case["base_mode"] & MAV_MODE_FLAG_CUSTOM_MODE_ENABLED)
        if case["expected_mode"] == "BASE_MODE_ONLY":
            assert not has_custom, f"Fixture mislabelled: {case}"
        else:
            assert has_custom, f"Fixture missing CUSTOM_MODE_ENABLED bit: {case}"
