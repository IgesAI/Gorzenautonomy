"""Mission planning service.

Manages mission waypoints, uploads/downloads to PX4 via MAVSDK,
and provides mission analysis (distance, duration estimates).
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Any, cast

logger = logging.getLogger(__name__)

try:
    from mavsdk.mission import MissionItem, MissionPlan

    MAVSDK_AVAILABLE = True
except ImportError:
    MAVSDK_AVAILABLE = False


@dataclass
class Waypoint:
    """Single mission waypoint."""

    latitude_deg: float
    longitude_deg: float
    altitude_m: float  # relative to home/takeoff
    speed_ms: float = 15.0
    loiter_time_s: float = 0.0
    acceptance_radius_m: float = 5.0
    camera_action: str = "none"  # none, photo, start_video, stop_video
    gimbal_pitch_deg: float = -90.0
    yaw_deg: float = float("nan")  # NaN = auto heading
    is_fly_through: bool = True
    order: int = 0


@dataclass
class MissionAnalysis:
    """Analysis results for a planned mission."""

    total_distance_m: float = 0.0
    total_distance_nmi: float = 0.0
    leg_distances_m: list[float] = field(default_factory=list)
    estimated_duration_s: float = 0.0
    estimated_duration_min: float = 0.0
    max_altitude_m: float = 0.0
    min_altitude_m: float = 0.0
    waypoint_count: int = 0
    avg_speed_ms: float = 0.0
    terrain_profile: list[float] = field(default_factory=list)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in meters between two points."""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate initial bearing from point 1 to point 2 in degrees."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    x = math.sin(dlam) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def analyze_mission(waypoints: list[Waypoint]) -> MissionAnalysis:
    """Analyze a mission plan and compute distance, duration, etc."""
    if not waypoints:
        return MissionAnalysis()

    distances: list[float] = []
    total_dist = 0.0
    total_time = 0.0

    for i in range(1, len(waypoints)):
        prev = waypoints[i - 1]
        curr = waypoints[i]
        horiz = _haversine(
            prev.latitude_deg, prev.longitude_deg, curr.latitude_deg, curr.longitude_deg
        )
        vert = abs(curr.altitude_m - prev.altitude_m)
        dist = math.sqrt(horiz**2 + vert**2)
        distances.append(dist)
        total_dist += dist

        speed = curr.speed_ms if curr.speed_ms > 0 else 15.0
        leg_time = dist / speed
        total_time += leg_time + curr.loiter_time_s

    altitudes = [w.altitude_m for w in waypoints]
    speeds = [w.speed_ms for w in waypoints if w.speed_ms > 0]

    return MissionAnalysis(
        total_distance_m=round(total_dist, 1),
        total_distance_nmi=round(total_dist / 1852, 2),
        leg_distances_m=[round(d, 1) for d in distances],
        estimated_duration_s=round(total_time, 1),
        estimated_duration_min=round(total_time / 60, 1),
        max_altitude_m=max(altitudes) if altitudes else 0,
        min_altitude_m=min(altitudes) if altitudes else 0,
        waypoint_count=len(waypoints),
        avg_speed_ms=round(sum(speeds) / len(speeds), 1) if speeds else 0,
    )


def waypoints_to_geojson(waypoints: list[Waypoint]) -> dict[str, Any]:
    """Convert waypoints to GeoJSON for map display."""
    features: list[dict[str, Any]] = []

    # Waypoint markers
    for i, wp in enumerate(waypoints):
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [wp.longitude_deg, wp.latitude_deg, wp.altitude_m],
                },
                "properties": {
                    "order": i,
                    "altitude_m": wp.altitude_m,
                    "speed_ms": wp.speed_ms,
                    "loiter_time_s": wp.loiter_time_s,
                    "camera_action": wp.camera_action,
                },
            }
        )

    # Flight path line
    if len(waypoints) >= 2:
        coords = [[wp.longitude_deg, wp.latitude_deg, wp.altitude_m] for wp in waypoints]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {"type": "flight_path"},
            }
        )

    return {"type": "FeatureCollection", "features": features}


class MissionService:
    """Mission management with optional MAVSDK drone connection."""

    def __init__(self) -> None:
        self._waypoints: list[Waypoint] = []
        self._system: Any = None

    @property
    def waypoints(self) -> list[Waypoint]:
        return self._waypoints

    def set_waypoints(self, waypoints: list[Waypoint]) -> MissionAnalysis:
        """Set the current mission plan and return analysis."""
        self._waypoints = waypoints
        for i, wp in enumerate(waypoints):
            wp.order = i
        return analyze_mission(waypoints)

    def add_waypoint(self, wp: Waypoint) -> MissionAnalysis:
        """Add a waypoint to the current plan."""
        wp.order = len(self._waypoints)
        self._waypoints.append(wp)
        return analyze_mission(self._waypoints)

    def remove_waypoint(self, index: int) -> MissionAnalysis:
        """Remove a waypoint by index."""
        if 0 <= index < len(self._waypoints):
            self._waypoints.pop(index)
            for i, wp in enumerate(self._waypoints):
                wp.order = i
        return analyze_mission(self._waypoints)

    def clear(self) -> None:
        """Clear all waypoints."""
        self._waypoints.clear()

    def get_analysis(self) -> MissionAnalysis:
        return analyze_mission(self._waypoints)

    def get_geojson(self) -> dict[str, Any]:
        return waypoints_to_geojson(self._waypoints)

    def get_waypoints(self) -> list[Waypoint]:
        """Return a copy of the current mission waypoints (API / router compatibility)."""
        return list(self._waypoints)

    async def upload_to_drone(self, system_address: str = "udp://:14540") -> dict[str, Any]:
        """Upload current mission to PX4 via MAVSDK."""
        if not MAVSDK_AVAILABLE:
            return {"success": False, "error": "MAVSDK not installed"}

        if not self._waypoints:
            return {"success": False, "error": "No waypoints in mission"}

        try:
            from gorzen.services.mavsdk_connection import get_mavsdk_system

            drone = await get_mavsdk_system(system_address)

            items = []
            item_cls = cast(Any, MissionItem)
            for wp in self._waypoints:
                items.append(
                    item_cls(
                        latitude_deg=wp.latitude_deg,
                        longitude_deg=wp.longitude_deg,
                        relative_altitude_m=wp.altitude_m,
                        speed_m_s=wp.speed_ms,
                        is_fly_through=wp.is_fly_through,
                        gimbal_pitch_deg=wp.gimbal_pitch_deg,
                        gimbal_yaw_deg=float("nan"),
                        loiter_time_s=wp.loiter_time_s,
                        acceptance_radius_m=wp.acceptance_radius_m,
                        yaw_deg=float("nan"),
                        camera_action=MissionItem.CameraAction.NONE,
                        camera_photo_interval_s=float("nan"),
                        camera_photo_distance_m=float("nan"),
                        vehicle_action=MissionItem.VehicleAction.NONE,
                    )
                )

            plan = MissionPlan(items)
            await drone.mission.upload_mission(plan)

            return {
                "success": True,
                "waypoints_uploaded": len(items),
            }
        except Exception:
            logger.exception("MAVSDK mission upload failed")
            return {
                "success": False,
                "error": "Mission upload failed. Check drone connection and try again.",
            }

    async def download_from_drone(self, system_address: str = "udp://:14540") -> dict[str, Any]:
        """Download current mission from PX4 via MAVSDK."""
        if not MAVSDK_AVAILABLE:
            return {"success": False, "error": "MAVSDK not installed"}

        try:
            from gorzen.services.mavsdk_connection import get_mavsdk_system

            drone = await get_mavsdk_system(system_address)

            plan = await drone.mission.download_mission()

            self._waypoints = []
            for i, item in enumerate(plan.mission_items):
                self._waypoints.append(
                    Waypoint(
                        latitude_deg=item.latitude_deg,
                        longitude_deg=item.longitude_deg,
                        altitude_m=item.relative_altitude_m,
                        speed_ms=item.speed_m_s,
                        loiter_time_s=item.loiter_time_s,
                        is_fly_through=item.is_fly_through,
                        gimbal_pitch_deg=item.gimbal_pitch_deg,
                        order=i,
                    )
                )

            return {
                "success": True,
                "waypoints_downloaded": len(self._waypoints),
                "analysis": analyze_mission(self._waypoints).__dict__,
            }
        except Exception:
            logger.exception("MAVSDK mission download failed")
            return {
                "success": False,
                "error": "Mission download failed. Check drone connection and try again.",
            }


def waypoints_to_json(waypoints: list[Waypoint]) -> list[dict[str, Any]]:
    """Serialize waypoints for JSON/DB storage."""
    out: list[dict[str, Any]] = []
    for w in waypoints:
        yaw = w.yaw_deg
        if isinstance(yaw, float) and math.isnan(yaw):
            yaw_val: float | None = None
        else:
            yaw_val = yaw
        out.append(
            {
                "latitude_deg": w.latitude_deg,
                "longitude_deg": w.longitude_deg,
                "altitude_m": w.altitude_m,
                "speed_ms": w.speed_ms,
                "loiter_time_s": w.loiter_time_s,
                "acceptance_radius_m": w.acceptance_radius_m,
                "camera_action": w.camera_action,
                "gimbal_pitch_deg": w.gimbal_pitch_deg,
                "yaw_deg": yaw_val,
                "is_fly_through": w.is_fly_through,
                "order": w.order,
            }
        )
    return out


def waypoints_from_json(data: list[dict[str, Any]]) -> list[Waypoint]:
    """Restore waypoints from persisted JSON."""
    wps: list[Waypoint] = []
    for d in data:
        raw_yaw = d.get("yaw_deg")
        if raw_yaw is None:
            yaw = float("nan")
        else:
            yaw = float(raw_yaw)
        wps.append(
            Waypoint(
                latitude_deg=float(d["latitude_deg"]),
                longitude_deg=float(d["longitude_deg"]),
                altitude_m=float(d["altitude_m"]),
                speed_ms=float(d.get("speed_ms", 15.0)),
                loiter_time_s=float(d.get("loiter_time_s", 0.0)),
                acceptance_radius_m=float(d.get("acceptance_radius_m", 5.0)),
                camera_action=str(d.get("camera_action", "none")),
                gimbal_pitch_deg=float(d.get("gimbal_pitch_deg", -90.0)),
                yaw_deg=yaw,
                is_fly_through=bool(d.get("is_fly_through", True)),
                order=int(d.get("order", len(wps))),
            )
        )
    return wps
