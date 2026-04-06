"""MAVLink MISSION_ITEM_INT coordinate encoding and frame conventions.

``MissionRaw`` / ``MISSION_ITEM_INT`` use latitude/longitude scaled by 1e7 as int32.
MAVLink recommends ``MAV_FRAME_GLOBAL_*_INT`` frames with this encoding (not mixed
with non-INT global frames). See MAVLink ``MISSION_ITEM_INT`` message docs.

Internal mission item dicts use **degrees** in ``x``/``y`` (latitude/longitude) unless
values are already scaled (magnitude outside degree ranges), for round-trip safety
with exports that pre-scale.
"""

from __future__ import annotations

from typing import Any

# common.xml: MAV_FRAME_GLOBAL_RELATIVE_ALT_INT — use with int lat/lon * 1e7
MAV_FRAME_GLOBAL_RELATIVE_ALT_INT = 11
# Legacy QGC / many docs use frame 3 (MAV_FRAME_GLOBAL_RELATIVE_ALT) with *float* lat/lon
MAV_FRAME_GLOBAL_RELATIVE_ALT = 3


def latlon_degrees_to_mavlink_int(lat_deg: float, lon_deg: float) -> tuple[int, int]:
    """Encode WGS-84 lat/lon degrees as MISSION_ITEM_INT x/y (1e7 scaling)."""
    return int(round(lat_deg * 1e7)), int(round(lon_deg * 1e7))


def normalize_xy_to_mavlink_int(x: Any, y: Any) -> tuple[int, int]:
    """Convert item ``x``/``y`` to MAVLink int lat/lon.

    - If values look like **degrees** (|lat|<=90, |lon|<=180), scale by 1e7.
    - Otherwise treat as **already** MISSION_ITEM_INT scaled (e.g. from
      ``export_px4_mission`` legacy int or large floats).
    """
    xf = float(x)
    yf = float(y)
    if abs(xf) <= 90.0 + 1e-6 and abs(yf) <= 180.0 + 1e-6:
        return latlon_degrees_to_mavlink_int(xf, yf)
    return int(round(xf)), int(round(yf))


def normalize_mission_frame_for_raw_upload(frame: Any) -> int:
    """Use INT global frame when uploading MissionRaw items with int lat/lon."""
    f = int(frame) if frame is not None else MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
    # Map legacy float-frame 3 to INT variant for encoded positions
    if f == MAV_FRAME_GLOBAL_RELATIVE_ALT:
        return MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
    return f
