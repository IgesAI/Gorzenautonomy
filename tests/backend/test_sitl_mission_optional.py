"""
Optional SITL / hardware-in-the-loop mission roundtrip checks.

Set environment variable ``GORZEN_SITL=1`` and run a PX4 SITL (or vehicle) reachable
at the default MAVLink UDP endpoint before enabling these tests. They are skipped
in normal CI to avoid flakiness and missing simulators.

Example (manual):

  export GORZEN_SITL=1
  cd backend && PYTHONPATH=src pytest tests/backend/test_sitl_mission_optional.py -v
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("GORZEN_SITL", "").strip() not in ("1", "true", "yes"),
    reason="Set GORZEN_SITL=1 with PX4 SITL (or vehicle) available for UDP mission upload roundtrip",
)


def test_execution_upload_roundtrip_placeholder() -> None:
    """Placeholder: extend with MAVSDK mission upload + download against SITL.

    Implementation sketch (when SITL is standard in CI):
    - Connect MAVSDK to udp://:14540
    - Build minimal RawMissionItem list from mavlink_mission_coords helpers
    - Upload, download, assert waypoint count and lat/lon within tolerance
    """
    pytest.skip(
        "GORZEN_SITL is set but automated SITL harness is not yet wired in CI; "
        "use manual QGC + /execution/upload validation until harness lands."
    )
