"""Mission planner with MAVLink mission item export and gimbal protocol."""

from __future__ import annotations

import math

from gorzen.solver.coverage import (
    generate_coverage_waypoints_drone_flightplan,
    optimize_waypoint_order_ortools,
)
from gorzen.schemas.mission import (
    GimbalAction,
    MissionPlan,
    MissionPlanRequest,
    MissionPlanResponse,
    PayloadAction,
    Waypoint,
    WaypointType,
)
from gorzen.schemas.twin_graph import VehicleTwin
from gorzen.solver.envelope_solver import _extract_params
from gorzen.solver.trajectory import TrajectoryOptimizer


def generate_survey_waypoints(
    area: list[tuple[float, float]],
    altitude_m: float,
    gsd_params: dict[str, float],
    overlap_pct: float = 70.0,
    sidelap_pct: float = 65.0,
) -> list[tuple[float, float]]:
    """Generate a lawnmower survey pattern within the given area polygon."""
    if len(area) < 3:
        return area

    lats = [p[0] for p in area]
    lons = [p[1] for p in area]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    sw = gsd_params.get("sensor_width_mm", 13.2)
    sh = gsd_params.get("sensor_height_mm", 8.8)
    fl = gsd_params.get("focal_length_mm", 24.0)
    px_w = gsd_params.get("pixel_width", 4000)
    px_h = gsd_params.get("pixel_height", 3000)

    gsd_w = sw * altitude_m / (fl * px_w)
    gsd_h = sh * altitude_m / (fl * px_h)
    footprint_w = gsd_w * px_w
    footprint_h = gsd_h * px_h

    line_spacing = footprint_w * (1.0 - sidelap_pct / 100.0)
    along_spacing = footprint_h * (1.0 - overlap_pct / 100.0)

    # Convert spacing to degrees (rough)
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians((min_lat + max_lat) / 2))

    line_spacing_deg = line_spacing / m_per_deg_lon
    along_spacing_deg = along_spacing / m_per_deg_lat

    waypoints: list[tuple[float, float]] = []
    lon = min_lon
    direction = 1
    while lon <= max_lon:
        if direction == 1:
            lat = min_lat
            while lat <= max_lat:
                waypoints.append((lat, lon))
                lat += along_spacing_deg
        else:
            lat = max_lat
            while lat >= min_lat:
                waypoints.append((lat, lon))
                lat -= along_spacing_deg
        lon += line_spacing_deg
        direction *= -1

    return waypoints


def plan_mission(
    twin: VehicleTwin,
    request: MissionPlanRequest,
) -> MissionPlanResponse:
    """Generate a complete mission plan from twin config and request."""
    params = _extract_params(twin)
    gsd_params = {
        "sensor_width_mm": params["sensor_width_mm"],
        "sensor_height_mm": params["sensor_height_mm"],
        "focal_length_mm": params["focal_length_mm"],
        "pixel_width": params["pixel_width"],
        "pixel_height": params["pixel_height"],
    }

    # Determine altitude from GSD requirement
    if request.altitude_m:
        alt = request.altitude_m
    else:
        sw = gsd_params["sensor_width_mm"]
        fl = gsd_params["focal_length_mm"]
        px_w = gsd_params["pixel_width"]
        alt = request.target_gsd_cm_px * fl * px_w / (sw * 100.0) * 0.9
        alt = max(alt, 10.0)

    # Generate waypoints: prefer drone-flightplan when available, else internal lawnmower
    if request.area_of_interest:
        df_wp = generate_coverage_waypoints_drone_flightplan(
            request.area_of_interest,
            alt,
            request.target_gsd_cm_px,
            request.overlap_pct,
            request.sidelap_pct,
            take_off=request.area_of_interest[0] if request.area_of_interest else None,
        )
        if df_wp:
            wp_coords = [(p[0], p[1]) for p in df_wp]
            if request.optimize:
                order = optimize_waypoint_order_ortools(wp_coords, depot=wp_coords[0])
                wp_coords = [wp_coords[i] for i in order]
        else:
            wp_coords = generate_survey_waypoints(
                request.area_of_interest, alt, gsd_params,
                request.overlap_pct, request.sidelap_pct,
            )
    else:
        wp_coords = [(0.0, 0.0), (0.001, 0.0), (0.001, 0.001), (0.0, 0.001)]

    # Optimize trajectory
    optimizer = TrajectoryOptimizer(gsd_params=gsd_params)
    # Energy budget: use fuel endurance for ICE, or battery for pure-electric
    tank_kg = params.get("tank_capacity_kg", 15.0)
    fuel_reserve = params.get("fuel_reserve_pct", 15.0) / 100.0
    bsfc = params.get("bsfc_cruise_g_kwh", 500.0)
    params.get("max_power_kw", 2.2)
    usable_fuel_g = tank_kg * 1000.0 * (1.0 - fuel_reserve)
    energy_budget = usable_fuel_g / (bsfc + 1e-6)  # kW-hr available

    if request.flight_speed_ms:
        speed_bounds = (request.flight_speed_ms * 0.9, request.flight_speed_ms * 1.1)
    else:
        speed_bounds = (2.0, params.get("max_speed_ms", 25.0) * 0.7)

    traj = optimizer.optimize_survey(
        wp_coords,
        altitude_bounds=(alt * 0.9, alt * 1.1),
        speed_bounds=speed_bounds,
        energy_budget_wh=energy_budget,
        target_gsd_cm=request.target_gsd_cm_px,
        max_blur_px=0.5,
        overlap_pct=request.overlap_pct,
    )

    # Build waypoint list
    waypoints: list[Waypoint] = []
    payload_actions: list[PayloadAction] = []

    # Takeoff
    waypoints.append(Waypoint(
        sequence=0,
        wp_type=WaypointType.TAKEOFF,
        latitude_deg=wp_coords[0][0],
        longitude_deg=wp_coords[0][1],
        altitude_m=alt,
        speed_ms=2.0,
    ))

    for i, (lat, lon) in enumerate(wp_coords):
        seq = i + 1
        waypoints.append(Waypoint(
            sequence=seq,
            wp_type=WaypointType.PHOTO,
            latitude_deg=lat,
            longitude_deg=lon,
            altitude_m=alt,
            speed_ms=traj.optimal_speed_ms,
        ))
        payload_actions.append(PayloadAction(
            waypoint_sequence=seq,
            action_type="photo",
            gimbal=GimbalAction(pitch_deg=-90.0),
        ))

    # RTL
    waypoints.append(Waypoint(
        sequence=len(wp_coords) + 1,
        wp_type=WaypointType.RETURN_TO_LAUNCH,
        latitude_deg=wp_coords[0][0],
        longitude_deg=wp_coords[0][1],
        altitude_m=alt,
    ))

    # Build MAVLink items
    mavlink_items = _build_mavlink_items(waypoints, payload_actions)

    plan = MissionPlan(
        twin_id=str(twin.twin_id),
        waypoints=waypoints,
        payload_actions=payload_actions,
        estimated_duration_s=traj.total_duration_s,
        estimated_energy_wh=traj.total_energy_wh,
        estimated_distance_m=traj.total_distance_m,
        mavlink_items=mavlink_items,
    )

    warnings: list[str] = []
    if traj.solver_status != "optimal":
        warnings.append(f"Trajectory solver status: {traj.solver_status}")
    if traj.total_energy_wh > energy_budget:
        warnings.append("Estimated energy exceeds budget")

    envelope_summary = {
        "optimal_speed_ms": traj.optimal_speed_ms,
        "optimal_altitude_m": traj.optimal_altitude_m,
        "total_photos": float(len(wp_coords)),
    }

    return MissionPlanResponse(
        plan=plan,
        envelope_summary=envelope_summary,
        warnings=warnings,
    )


def _build_mavlink_items(
    waypoints: list[Waypoint],
    payload_actions: list[PayloadAction],
) -> list[dict]:
    """Convert waypoints and payload actions to MAVLink mission items."""
    items: list[dict] = []

    for wp in waypoints:
        cmd_map = {
            WaypointType.TAKEOFF: 22,
            WaypointType.NAVIGATE: 16,
            WaypointType.PHOTO: 16,
            WaypointType.LOITER: 17,
            WaypointType.RETURN_TO_LAUNCH: 20,
            WaypointType.LAND: 21,
            WaypointType.INSPECT: 16,
        }
        cmd = cmd_map.get(wp.wp_type, 16)

        item = {
            "seq": wp.sequence,
            "frame": 3,  # MAV_FRAME_GLOBAL_RELATIVE_ALT
            "command": cmd,
            "current": 1 if wp.sequence == 0 else 0,
            "autocontinue": 1,
            "param1": wp.hold_time_s,
            "param2": wp.acceptance_radius_m,
            "param3": 0,
            "param4": float("nan"),
            "x": wp.latitude_deg,
            "y": wp.longitude_deg,
            "z": wp.altitude_m,
        }
        items.append(item)

    # Add camera trigger commands for photo waypoints
    photo_seqs = {pa.waypoint_sequence for pa in payload_actions if pa.action_type == "photo"}
    for seq in sorted(photo_seqs):
        items.append({
            "seq": 1000 + seq,
            "frame": 2,
            "command": 203,  # MAV_CMD_DO_DIGICAM_CONTROL
            "param1": 0, "param2": 0, "param3": 0, "param4": 0,
            "param5": 1,  # trigger
            "x": 0, "y": 0, "z": 0,
        })

    return items
