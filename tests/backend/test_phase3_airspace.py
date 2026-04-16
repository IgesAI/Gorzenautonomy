"""Phase 3c regression tests — airspace, NOTAM, and Remote ID."""

from __future__ import annotations

import pytest

from gorzen.schemas.mission import MissionPlan, Waypoint, WaypointType
from gorzen.services.airspace import (
    AirspaceCatalog,
    AirspaceClass,
    AirspaceVolume,
    Notam,
    OpenDroneIdEmitter,
    RemoteIdConfig,
    find_airspace_intersections,
    notams_intersecting_mission,
)


def _plan(alts: list[float], lats: list[float] | None = None, lons: list[float] | None = None) -> MissionPlan:
    lats = lats or [37.0, 37.02, 37.04]
    lons = lons or [-122.0, -122.02, -122.04]
    wps = [
        Waypoint(
            sequence=i,
            wp_type=WaypointType.NAVIGATE,
            latitude_deg=la,
            longitude_deg=lo,
            altitude_m=a,
        )
        for i, (la, lo, a) in enumerate(zip(lats, lons, alts, strict=True))
    ]
    return MissionPlan(twin_id="t", waypoints=wps)


class TestAirspaceIntersection:
    def test_leg_crossing_polygon_detected(self) -> None:
        catalog = AirspaceCatalog(
            volumes=[
                AirspaceVolume(
                    identifier="R-2508",
                    name="Restricted",
                    airspace_class=AirspaceClass.RESTRICTED,
                    polygon=[
                        (37.01, -122.03),
                        (37.01, -122.01),
                        (37.03, -122.01),
                        (37.03, -122.03),
                    ],
                    floor_m_msl=0.0,
                    ceiling_m_msl=500.0,
                )
            ]
        )
        plan = _plan([100.0, 100.0, 100.0])
        hits = find_airspace_intersections(plan, catalog)
        assert hits, "Expected at least one intersection"
        assert hits[0].volume.identifier == "R-2508"

    def test_altitude_above_ceiling_not_flagged(self) -> None:
        catalog = AirspaceCatalog(
            volumes=[
                AirspaceVolume(
                    identifier="LOW",
                    name="Low",
                    airspace_class=AirspaceClass.RESTRICTED,
                    polygon=[
                        (37.01, -122.03),
                        (37.01, -122.01),
                        (37.03, -122.01),
                        (37.03, -122.03),
                    ],
                    floor_m_msl=0.0,
                    ceiling_m_msl=50.0,
                )
            ]
        )
        plan = _plan([500.0, 500.0, 500.0])
        assert find_airspace_intersections(plan, catalog) == []

    def test_expired_volume_filtered(self) -> None:
        catalog = AirspaceCatalog(
            volumes=[
                AirspaceVolume(
                    identifier="OLD",
                    name="Expired TFR",
                    airspace_class=AirspaceClass.TFR,
                    polygon=[
                        (37.01, -122.03),
                        (37.01, -122.01),
                        (37.03, -122.01),
                        (37.03, -122.03),
                    ],
                    floor_m_msl=0.0,
                    ceiling_m_msl=500.0,
                    active_until=100.0,  # 1970
                )
            ]
        )
        plan = _plan([100.0, 100.0, 100.0])
        assert find_airspace_intersections(plan, catalog) == []


class TestNotams:
    def test_notam_near_leg_detected(self) -> None:
        plan = _plan([100.0, 100.0, 100.0])
        n = Notam(
            id="!FDC 1/1234",
            title="Presidential Movement",
            issued_iso="",
            effective_from_iso="",
            effective_to_iso="",
            center_lat=37.02,
            center_lon=-122.02,
            radius_nmi=1.0,
        )
        hits = notams_intersecting_mission(plan, [n])
        assert len(hits) == 1

    def test_notam_far_away_ignored(self) -> None:
        plan = _plan([100.0, 100.0, 100.0])
        n = Notam(
            id="!FDC far",
            title="Far",
            issued_iso="",
            effective_from_iso="",
            effective_to_iso="",
            center_lat=40.0,
            center_lon=-120.0,
            radius_nmi=2.0,
        )
        assert notams_intersecting_mission(plan, [n]) == []


class TestRemoteId:
    def test_emitter_refuses_when_disabled(self) -> None:
        cfg = RemoteIdConfig(uas_id="SN12345", uas_id_type=1, enabled=False)
        emit = OpenDroneIdEmitter(cfg, sender=lambda _n, _f: None)
        with pytest.raises(RuntimeError):
            emit.build_basic_id_message()
        with pytest.raises(RuntimeError):
            emit.emit_once()

    def test_emitter_sends_three_messages_when_enabled(self) -> None:
        sent: list[tuple[str, dict]] = []

        def _sender(name: str, fields: dict) -> None:
            sent.append((name, fields))

        cfg = RemoteIdConfig(
            uas_id="SN12345",
            uas_id_type=1,
            operator_id="OP9999",
            self_id="VTOL-TEST",
            enabled=True,
        )
        emit = OpenDroneIdEmitter(cfg, sender=_sender)
        msgs = emit.emit_once()
        assert msgs == [
            "OPEN_DRONE_ID_BASIC_ID",
            "OPEN_DRONE_ID_SELF_ID",
            "OPEN_DRONE_ID_OPERATOR_ID",
        ]
        assert len(sent) == 3
        assert sent[0][1]["id_type"] == 1
        # uas_id is padded to 20 bytes.
        assert len(sent[0][1]["uas_id"]) == 20
