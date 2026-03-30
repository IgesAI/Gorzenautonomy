"""Mission export formats: QGroundControl .plan JSON, KML, PX4 mission file.

Converts internal MissionPlan to standard autopilot-compatible formats.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

from gorzen.schemas.mission import MissionPlan, Waypoint, WaypointType


def export_qgc_plan(plan: MissionPlan) -> dict[str, Any]:
    """Export mission plan as QGroundControl .plan JSON format.

    Reference: https://dev.qgroundcontrol.com/master/en/file_formats/plan.html
    """
    items: list[dict[str, Any]] = []

    for wp in plan.waypoints:
        cmd = _wp_type_to_mav_cmd(wp.wp_type)
        item: dict[str, Any] = {
            "autoContinue": True,
            "command": cmd,
            "doJumpId": wp.sequence + 1,
            "frame": 3,  # MAV_FRAME_GLOBAL_RELATIVE_ALT
            "params": [
                wp.hold_time_s,
                wp.acceptance_radius_m,
                0,
                float("nan"),
                wp.latitude_deg,
                wp.longitude_deg,
                wp.altitude_m,
            ],
            "type": "SimpleItem",
        }
        items.append(item)

    qgc_plan = {
        "fileType": "Plan",
        "geoFence": {"circles": [], "polygons": [], "version": 2},
        "groundStation": "Gorzen Autonomy Platform",
        "mission": {
            "cruiseSpeed": plan.waypoints[1].speed_ms if len(plan.waypoints) > 1 else 10.0,
            "firmwareType": 12,  # PX4
            "globalPlanAltitudeMode": 1,
            "hoverSpeed": 5.0,
            "items": items,
            "plannedHomePosition": [
                plan.waypoints[0].latitude_deg if plan.waypoints else 0,
                plan.waypoints[0].longitude_deg if plan.waypoints else 0,
                plan.waypoints[0].altitude_m if plan.waypoints else 0,
            ],
            "vehicleType": 20,  # VTOL
            "version": 2,
        },
        "rallyPoints": {"points": [], "version": 2},
        "version": 1,
    }

    return qgc_plan


def export_qgc_plan_json(plan: MissionPlan) -> str:
    """Export as QGC .plan JSON string."""
    return json.dumps(export_qgc_plan(plan), indent=2)


def export_kml(plan: MissionPlan, name: str = "Gorzen Mission") -> str:
    """Export mission plan as KML for Google Earth / visualization.

    Includes the flight path as a LineString and waypoints as Placemarks.
    """
    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = name
    ET.SubElement(doc, "description").text = (
        f"Mission plan: {len(plan.waypoints)} waypoints, "
        f"{plan.estimated_distance_m:.0f}m distance, "
        f"{plan.estimated_duration_s:.0f}s duration"
    )

    # Flight path line
    path_folder = ET.SubElement(doc, "Folder")
    ET.SubElement(path_folder, "name").text = "Flight Path"

    line_pm = ET.SubElement(path_folder, "Placemark")
    ET.SubElement(line_pm, "name").text = "Route"
    line_style = ET.SubElement(line_pm, "Style")
    line_ls = ET.SubElement(line_style, "LineStyle")
    ET.SubElement(line_ls, "color").text = "ff0066ff"
    ET.SubElement(line_ls, "width").text = "3"

    line_str = ET.SubElement(line_pm, "LineString")
    ET.SubElement(line_str, "altitudeMode").text = "relativeToGround"
    coords_text = " ".join(
        f"{wp.longitude_deg},{wp.latitude_deg},{wp.altitude_m}"
        for wp in plan.waypoints
    )
    ET.SubElement(line_str, "coordinates").text = coords_text

    # Waypoints as placemarks
    wp_folder = ET.SubElement(doc, "Folder")
    ET.SubElement(wp_folder, "name").text = "Waypoints"

    for wp in plan.waypoints:
        pm = ET.SubElement(wp_folder, "Placemark")
        ET.SubElement(pm, "name").text = f"WP{wp.sequence} ({wp.wp_type.value})"
        desc = f"Alt: {wp.altitude_m}m AGL"
        if wp.speed_ms:
            desc += f", Speed: {wp.speed_ms}m/s"
        ET.SubElement(pm, "description").text = desc
        point = ET.SubElement(pm, "Point")
        ET.SubElement(point, "altitudeMode").text = "relativeToGround"
        ET.SubElement(point, "coordinates").text = (
            f"{wp.longitude_deg},{wp.latitude_deg},{wp.altitude_m}"
        )

    return ET.tostring(kml, encoding="unicode", xml_declaration=True)


def export_px4_mission(plan: MissionPlan) -> list[dict[str, Any]]:
    """Export as PX4 MissionRaw items (compatible with MAVSDK upload).

    Each item follows MAVLink MISSION_ITEM_INT format.
    """
    items: list[dict[str, Any]] = []

    for wp in plan.waypoints:
        cmd = _wp_type_to_mav_cmd(wp.wp_type)
        item = {
            "seq": wp.sequence,
            "frame": 3,  # MAV_FRAME_GLOBAL_RELATIVE_ALT
            "command": cmd,
            "current": 1 if wp.sequence == 0 else 0,
            "autocontinue": 1,
            "param1": wp.hold_time_s,
            "param2": wp.acceptance_radius_m,
            "param3": 0.0,
            "param4": float("nan"),
            "x": int(wp.latitude_deg * 1e7),
            "y": int(wp.longitude_deg * 1e7),
            "z": wp.altitude_m,
            "mission_type": 0,
        }
        items.append(item)

    return items


def _wp_type_to_mav_cmd(wp_type: WaypointType) -> int:
    """Map internal waypoint type to MAVLink command ID."""
    return {
        WaypointType.TAKEOFF: 22,
        WaypointType.NAVIGATE: 16,
        WaypointType.PHOTO: 16,
        WaypointType.LOITER: 17,
        WaypointType.RETURN_TO_LAUNCH: 20,
        WaypointType.LAND: 21,
        WaypointType.INSPECT: 16,
    }.get(wp_type, 16)
