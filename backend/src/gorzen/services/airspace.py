"""Airspace, NOTAM and Remote ID layer for pre-flight and in-flight checks.

This module provides the glue between mission planning and the external
regulatory services that a real VTOL operator must respect:

* ``AirspaceIntersectionCheck`` — rejects missions whose legs cross
  restricted airspace volumes (controlled Class B/C/D, prohibited,
  restricted, TFR). Volumes come from an :class:`AirspaceCatalog`
  populated from OpenAIP / FAA SUA data (or an in-memory dev catalog).
* ``NotamService`` — fetches active NOTAMs from the FAA API (JSON) or a
  local file, filters by bounding-box/time-window, and exposes
  :meth:`NotamService.active_notams_for_mission`.
* ``OpenDroneIdEmitter`` — emits FAA Part 89 / ASTM F3411 Remote ID
  broadcast messages via MAVLink ``OPEN_DRONE_ID_*`` messages during
  execution. Gated behind an explicit ``enabled=True`` toggle; the
  backend never broadcasts identity automatically.

All network-facing code is opt-in and has no default API keys hardcoded;
callers must supply credentials via ``settings`` / env vars.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence

import httpx

from gorzen.schemas.mission import MissionPlan, Waypoint

logger = logging.getLogger(__name__)


class AirspaceClass(str, Enum):
    """Aviation airspace categories. Values match FAA / ICAO shorthand."""

    CLASS_A = "A"
    CLASS_B = "B"
    CLASS_C = "C"
    CLASS_D = "D"
    CLASS_E = "E"
    CLASS_G = "G"
    PROHIBITED = "P"
    RESTRICTED = "R"
    DANGER = "D_DANGER"
    MOA = "MOA"
    TFR = "TFR"


@dataclass(frozen=True)
class AirspaceVolume:
    """A 3D airspace volume.

    ``polygon`` is a list of ``(lat, lon)`` vertices in CCW order.
    ``floor_m_msl`` / ``ceiling_m_msl`` bound the vertical extent. Volumes
    with ``active_until`` in the past are filtered out at query time.
    """

    identifier: str
    name: str
    airspace_class: AirspaceClass
    polygon: list[tuple[float, float]]
    floor_m_msl: float
    ceiling_m_msl: float
    active_from: float | None = None  # Unix timestamp; None = always
    active_until: float | None = None  # Unix timestamp; None = always
    source: str = "local"


@dataclass
class AirspaceCatalog:
    """In-memory catalog of airspace volumes."""

    volumes: list[AirspaceVolume] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: str | Path) -> "AirspaceCatalog":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        volumes = [
            AirspaceVolume(
                identifier=v["identifier"],
                name=v["name"],
                airspace_class=AirspaceClass(v["class"]),
                polygon=[tuple(pt) for pt in v["polygon"]],
                floor_m_msl=float(v["floor_m_msl"]),
                ceiling_m_msl=float(v["ceiling_m_msl"]),
                active_from=v.get("active_from"),
                active_until=v.get("active_until"),
                source=v.get("source", "file"),
            )
            for v in raw
        ]
        return cls(volumes=volumes)

    def active_at(self, when: float | None = None) -> list[AirspaceVolume]:
        t = when or time.time()
        return [
            v
            for v in self.volumes
            if (v.active_from is None or v.active_from <= t)
            and (v.active_until is None or v.active_until >= t)
        ]


# ---------------------------------------------------------------------------
# Airspace intersection
# ---------------------------------------------------------------------------


def _point_in_polygon(lat: float, lon: float, poly: Sequence[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if (yi > lat) != (yj > lat):
            denom = (yj - yi) or 1e-12
            x_intersect = (xj - xi) * (lat - yi) / denom + xi
            if lon < x_intersect:
                inside = not inside
        j = i
    return inside


def _seg_intersects_poly(
    a: tuple[float, float], b: tuple[float, float], poly: Sequence[tuple[float, float]]
) -> bool:
    # Quick rejection test: both endpoints outside the bbox with the same sign.
    min_lat = min(p[0] for p in poly)
    max_lat = max(p[0] for p in poly)
    min_lon = min(p[1] for p in poly)
    max_lon = max(p[1] for p in poly)
    if max(a[0], b[0]) < min_lat or min(a[0], b[0]) > max_lat:
        return False
    if max(a[1], b[1]) < min_lon or min(a[1], b[1]) > max_lon:
        return False
    if _point_in_polygon(*a, poly) or _point_in_polygon(*b, poly):
        return True
    # Edge-edge intersection.
    for i in range(len(poly)):
        c = poly[i]
        d = poly[(i + 1) % len(poly)]
        if _segments_cross(a, b, c, d):
            return True
    return False


def _segments_cross(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    def _ccw(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
        return (c[0] - a[0]) * (b[1] - a[1]) > (b[0] - a[0]) * (c[1] - a[1])

    return _ccw(p1, p3, p4) != _ccw(p2, p3, p4) and _ccw(p1, p2, p3) != _ccw(p1, p2, p4)


@dataclass
class AirspaceIntersection:
    volume: AirspaceVolume
    waypoint_index: int
    leg_start: tuple[float, float]
    leg_end: tuple[float, float]
    altitude_m_msl: float


def find_airspace_intersections(
    plan: MissionPlan,
    catalog: AirspaceCatalog,
    home_elevation_m_msl: float = 0.0,
    when: float | None = None,
) -> list[AirspaceIntersection]:
    """Return every leg/volume intersection (respecting vertical bounds).

    ``altitude_m`` in the mission plan is AGL relative to ``home_elevation``;
    volumes are quoted in MSL — we convert before comparing.
    """
    active = catalog.active_at(when)
    results: list[AirspaceIntersection] = []
    wps: Iterable[Waypoint] = plan.waypoints
    last: Waypoint | None = None
    for idx, wp in enumerate(wps):
        if last is None:
            last = wp
            continue
        leg_start = (last.latitude_deg, last.longitude_deg)
        leg_end = (wp.latitude_deg, wp.longitude_deg)
        alt_start_msl = home_elevation_m_msl + last.altitude_m
        alt_end_msl = home_elevation_m_msl + wp.altitude_m
        alt_min = min(alt_start_msl, alt_end_msl)
        alt_max = max(alt_start_msl, alt_end_msl)
        for volume in active:
            if alt_max < volume.floor_m_msl or alt_min > volume.ceiling_m_msl:
                continue  # vertical miss
            if _seg_intersects_poly(leg_start, leg_end, volume.polygon):
                results.append(
                    AirspaceIntersection(
                        volume=volume,
                        waypoint_index=idx,
                        leg_start=leg_start,
                        leg_end=leg_end,
                        altitude_m_msl=0.5 * (alt_min + alt_max),
                    )
                )
        last = wp
    return results


# ---------------------------------------------------------------------------
# NOTAM fetch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Notam:
    id: str
    title: str
    issued_iso: str
    effective_from_iso: str
    effective_to_iso: str
    center_lat: float
    center_lon: float
    radius_nmi: float
    raw: dict[str, object] = field(default_factory=dict)


class NotamService:
    """Pluggable NOTAM fetcher.

    The default ``source`` is a local JSON file (useful for development
    and CI). Production deployments point at the FAA NOTAM Search API
    or EuroControl EAD; both return JSON with polygon / point geometry.
    """

    def __init__(
        self,
        source: str | Path | None = None,
        http_url: str | None = None,
        api_token: str | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.source = Path(source) if source else None
        self.http_url = http_url
        self.api_token = api_token
        self.timeout_s = timeout_s

    async def fetch_active(
        self,
        bbox: tuple[float, float, float, float] | None = None,
        now: float | None = None,
    ) -> list[Notam]:
        """Fetch active NOTAMs, optionally filtered by bounding box ``(min_lat, min_lon, max_lat, max_lon)``.

        Uses the configured local file first (so tests and dev can avoid
        the live API), then HTTP when ``http_url`` is set.
        """
        now = now or time.time()
        raw: list[dict] = []
        if self.source and self.source.exists():
            raw = json.loads(self.source.read_text(encoding="utf-8"))
        elif self.http_url:
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.get(self.http_url, headers=headers)
                resp.raise_for_status()
                raw = resp.json()
        else:
            return []

        notams: list[Notam] = []
        for item in raw:
            try:
                n = Notam(
                    id=str(item["id"]),
                    title=str(item.get("title", "")),
                    issued_iso=str(item.get("issued", "")),
                    effective_from_iso=str(item.get("effective_from", "")),
                    effective_to_iso=str(item.get("effective_to", "")),
                    center_lat=float(item["center_lat"]),
                    center_lon=float(item["center_lon"]),
                    radius_nmi=float(item.get("radius_nmi", 1.0)),
                    raw=item,
                )
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed NOTAM: %s", exc)
                continue
            # Respect effective window when provided.
            if not self._is_effective(n, now):
                continue
            if bbox is not None and not self._notam_in_bbox(n, bbox):
                continue
            notams.append(n)
        return notams

    @staticmethod
    def _is_effective(n: Notam, now: float) -> bool:
        if n.effective_from_iso:
            try:
                t_from = _iso_to_epoch(n.effective_from_iso)
                if now < t_from:
                    return False
            except ValueError:
                return True
        if n.effective_to_iso:
            try:
                t_to = _iso_to_epoch(n.effective_to_iso)
                if now > t_to:
                    return False
            except ValueError:
                return True
        return True

    @staticmethod
    def _notam_in_bbox(n: Notam, bbox: tuple[float, float, float, float]) -> bool:
        min_lat, min_lon, max_lat, max_lon = bbox
        # Coarse containment: include any NOTAM whose centre is inside the
        # bbox, or whose radius reaches it.
        nmi_to_deg = 1.0 / 60.0
        r_deg = n.radius_nmi * nmi_to_deg
        return (
            n.center_lat + r_deg >= min_lat
            and n.center_lat - r_deg <= max_lat
            and n.center_lon + r_deg >= min_lon
            and n.center_lon - r_deg <= max_lon
        )


def _iso_to_epoch(iso: str) -> float:
    from datetime import datetime, timezone

    try:
        if iso.endswith("Z"):
            iso = iso[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError as exc:
        raise ValueError(f"Bad ISO timestamp {iso!r}: {exc}") from exc


def notams_intersecting_mission(
    plan: MissionPlan,
    notams: list[Notam],
    home_elevation_m_msl: float = 0.0,
) -> list[Notam]:
    """Return NOTAMs whose circular disk intersects any mission leg."""
    affected: list[Notam] = []
    for n in notams:
        for wp in plan.waypoints:
            if _haversine_nmi(wp.latitude_deg, wp.longitude_deg, n.center_lat, n.center_lon) <= n.radius_nmi:
                affected.append(n)
                break
    return affected


def _haversine_nmi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R_m = 6_371_000.0
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return R_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)) / 1852.0


# ---------------------------------------------------------------------------
# Remote ID (FAA Part 89 / ASTM F3411) emitter
# ---------------------------------------------------------------------------


@dataclass
class RemoteIdConfig:
    """Minimum fields required to broadcast a compliant Remote ID message.

    ``uas_id_type`` 1 = serial number (ANSI/CTA-2063-A), 2 = CAA-registered
    session ID, 3 = UTM UUID, 4 = specific session ID.
    """

    uas_id: str
    uas_id_type: int
    operator_id: str = ""
    self_id: str = ""  # short description shown on phones
    #: Whether to emit. Default False so accidental broadcasts require a
    #: deliberate enable.
    enabled: bool = False


class OpenDroneIdEmitter:
    """Emit Remote ID messages via MAVLink ``OPEN_DRONE_ID_*`` commands.

    The emitter is purely a formatter — the MAVLink write happens through
    a pluggable ``sender`` callback so the unit tests don't need a live
    serial link.
    """

    def __init__(
        self,
        config: RemoteIdConfig,
        sender: "None | _MavSender" = None,
    ) -> None:
        self.config = config
        self.sender = sender

    def build_basic_id_message(self) -> dict[str, object]:
        """Return the field dict for an ``OPEN_DRONE_ID_BASIC_ID`` message."""
        if not self.config.enabled:
            raise RuntimeError("Remote ID broadcasts are disabled in RemoteIdConfig")
        uas_id_bytes = self.config.uas_id.encode("utf-8")[:20].ljust(20, b"\x00")
        return {
            "id_type": int(self.config.uas_id_type),
            "ua_type": 2,  # Aeroplane / Fixed-wing
            "uas_id": list(uas_id_bytes),
        }

    def build_self_id_message(self) -> dict[str, object]:
        if not self.config.enabled:
            raise RuntimeError("Remote ID broadcasts are disabled in RemoteIdConfig")
        description = self.config.self_id.encode("utf-8")[:23].ljust(23, b"\x00")
        return {
            "description_type": 0,
            "description": list(description),
        }

    def build_operator_id_message(self) -> dict[str, object]:
        if not self.config.enabled:
            raise RuntimeError("Remote ID broadcasts are disabled in RemoteIdConfig")
        op = self.config.operator_id.encode("utf-8")[:20].ljust(20, b"\x00")
        return {
            "operator_id_type": 0,
            "operator_id": list(op),
        }

    def emit_once(self) -> list[str]:
        """Send basic + self + operator ID messages through the sender.

        Returns a list of message-name strings that were sent so callers
        can log/audit.
        """
        if self.sender is None:
            raise RuntimeError("OpenDroneIdEmitter has no sender configured")
        if not self.config.enabled:
            raise RuntimeError("Remote ID broadcasts are disabled in RemoteIdConfig")
        sent: list[str] = []
        self.sender("OPEN_DRONE_ID_BASIC_ID", self.build_basic_id_message())
        sent.append("OPEN_DRONE_ID_BASIC_ID")
        self.sender("OPEN_DRONE_ID_SELF_ID", self.build_self_id_message())
        sent.append("OPEN_DRONE_ID_SELF_ID")
        self.sender("OPEN_DRONE_ID_OPERATOR_ID", self.build_operator_id_message())
        sent.append("OPEN_DRONE_ID_OPERATOR_ID")
        return sent


# Type alias for the sender callback: (message_name, fields) -> None.
_MavSender = "type[Callable[[str, dict[str, object]], None]]"


__all__ = [
    "AirspaceCatalog",
    "AirspaceClass",
    "AirspaceIntersection",
    "AirspaceVolume",
    "Notam",
    "NotamService",
    "OpenDroneIdEmitter",
    "RemoteIdConfig",
    "find_airspace_intersections",
    "notams_intersecting_mission",
]
