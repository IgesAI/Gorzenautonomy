"""Shared MAVSDK ``System`` access: reuse telemetry connection when available."""

from __future__ import annotations

import asyncio
from typing import Any

from gorzen.services.mavlink_telemetry import telemetry_service


async def get_mavsdk_system(connection_url: str = "udp://:14540") -> Any:
    """Return the telemetry service's connected ``System``, or connect a new one.

    When ``telemetry_service`` is already connected, its ``System`` is reused to avoid
    conflicting MAVLink sessions to the same endpoint.
    """
    shared = telemetry_service.get_connected_system()
    if shared is not None:
        return shared

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
