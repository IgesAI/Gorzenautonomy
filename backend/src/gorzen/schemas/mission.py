"""Mission planning schemas: waypoints, payload actions, MAVLink export."""

from __future__ import annotations

from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class WaypointType(str, Enum):
    NAVIGATE = "navigate"
    LOITER = "loiter"
    PHOTO = "photo"
    VIDEO_START = "video_start"
    VIDEO_STOP = "video_stop"
    INSPECT = "inspect"
    RETURN_TO_LAUNCH = "rtl"
    LAND = "land"
    TAKEOFF = "takeoff"
    # VTOL-specific mission items. Emitted as NAV_VTOL_TAKEOFF (84),
    # NAV_VTOL_LAND (85), and DO_VTOL_TRANSITION (3000). Required for any
    # QuadPlane / VTOL aircraft to transition between MC and FW.
    VTOL_TAKEOFF = "vtol_takeoff"
    VTOL_LAND = "vtol_land"
    TRANSITION_TO_FW = "transition_to_fw"
    TRANSITION_TO_MC = "transition_to_mc"
    #: Generic legacy transition marker — kept for backward compat. New
    #: callers should use TRANSITION_TO_FW / TRANSITION_TO_MC.
    TRANSITION = "transition"


class Waypoint(BaseModel):
    sequence: int
    wp_type: WaypointType
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    speed_ms: float | None = None
    hold_time_s: float = 0.0
    acceptance_radius_m: float = 2.0
    params: dict[str, float] = Field(default_factory=dict)


class GimbalAction(BaseModel):
    pitch_deg: float = -90.0
    yaw_deg: float = 0.0
    mode: str = "region_of_interest"


class PayloadAction(BaseModel):
    waypoint_sequence: int
    action_type: str  # "photo", "video_start", "video_stop", "set_zoom"
    gimbal: GimbalAction | None = None
    params: dict[str, float] = Field(default_factory=dict)


class MissionPlan(BaseModel):
    mission_id: UUID = Field(default_factory=uuid4)
    twin_id: str
    waypoints: list[Waypoint] = Field(default_factory=list)
    payload_actions: list[PayloadAction] = Field(default_factory=list)

    estimated_duration_s: float = 0.0
    estimated_energy_wh: float = 0.0
    estimated_distance_m: float = 0.0
    mission_completion_probability: float | None = None

    mavlink_items: list[dict] | None = None


class MissionPlanRequest(BaseModel):
    twin_id: str
    area_of_interest: list[tuple[float, float]] | None = None
    target_gsd_cm_px: float = 1.0
    overlap_pct: float = 70.0
    sidelap_pct: float = 65.0
    flight_speed_ms: float | None = None
    altitude_m: float | None = None
    optimize: bool = True


class MissionPlanResponse(BaseModel):
    plan: MissionPlan
    envelope_summary: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
