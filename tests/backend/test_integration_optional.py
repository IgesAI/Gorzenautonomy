"""Optional integration hooks (SITL, live UDP). Disabled unless env flags are set."""

from __future__ import annotations

import os

import pytest


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RUN_SITL") != "1", reason="Set RUN_SITL=1 to enable PX4 SITL integration tests")
def test_sitl_integration_placeholder() -> None:
    """When enabled, extend with: connect to local SITL, upload mission, assert mission_count.

    Run with: RUN_SITL=1 pytest tests/backend/test_integration_optional.py -m integration
    Requires docker compose sim profile or local PX4 SITL.
    """
    assert True
