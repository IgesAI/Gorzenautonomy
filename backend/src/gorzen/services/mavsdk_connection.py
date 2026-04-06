"""Shared MAVSDK ``System`` access for mission execution APIs.

Telemetry uses pymavlink (``mavutil``) in
:class:`gorzen.services.mavlink_telemetry.MAVLinkTelemetryService`; that object is
**not** a MAVSDK :class:`mavsdk.System` and must never be returned here — doing so
breaks ``mission_raw`` / ``mission`` upload paths at runtime.
"""

from __future__ import annotations

import asyncio
from typing import Any


async def get_mavsdk_system(connection_url: str = "udp://:14540") -> Any:
    """Connect and return a MAVSDK :class:`mavsdk.System` (never a pymavlink connection)."""

    try:
        from mavsdk import System
    except ImportError as e:
        raise RuntimeError("MAVSDK not installed") from e

    drone = System()
    await drone.connect(system_address=connection_url)

    async def _wait() -> None:
        async for state in drone.core.connection_state():
            if state.is_connected:
                return

    await asyncio.wait_for(_wait(), timeout=30.0)
    return drone
