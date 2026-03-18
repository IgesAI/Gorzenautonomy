export interface Waypoint {
  sequence: number;
  wp_type: string;
  latitude_deg: number;
  longitude_deg: number;
  altitude_m: number;
  speed_ms?: number;
  hold_time_s: number;
}

export interface PayloadAction {
  waypoint_sequence: number;
  action_type: string;
  gimbal?: { pitch_deg: number; yaw_deg: number; mode: string };
}

export interface MissionPlan {
  mission_id: string;
  twin_id: string;
  waypoints: Waypoint[];
  payload_actions: PayloadAction[];
  estimated_duration_s: number;
  estimated_energy_wh: number;
  estimated_distance_m: number;
  mission_completion_probability?: number;
}

export interface MissionPlanRequest {
  twin_id: string;
  area_of_interest?: [number, number][];
  target_gsd_cm_px: number;
  overlap_pct: number;
  sidelap_pct: number;
  flight_speed_ms?: number;
  altitude_m?: number;
  optimize: boolean;
}

export interface MissionPlanResponse {
  plan: MissionPlan;
  envelope_summary: Record<string, number>;
  warnings: string[];
}
