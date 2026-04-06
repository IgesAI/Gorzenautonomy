/** Shared API response shapes (align with FastAPI / Pydantic). */

export interface EndurancePreview {
  endurance_minutes_electrical: number;
  endurance_minutes_fuel: number;
  endurance_minutes_effective: number;
}

/** Minimal VehicleTwin shape as returned by the backend. */
export interface VehicleTwin {
  twin_id: string;
  name: string;
  description?: string;
  version?: { major: number; minor: number; patch: number };
  build_hash?: string;
  [key: string]: unknown;
}

/** /twins/schema response */
export interface TwinSchemaResponse {
  subsystems: Record<string, SubsystemSchema>;
  twin_id: string;
  version: { major: number; minor: number; patch: number };
}

export interface SubsystemSchema {
  label: string;
  description: string;
  parameters: Record<string, TypedParameter | unknown>;
}

export interface TypedParameter {
  value: number | string | boolean;
  units?: string;
  constraints?: { min?: number; max?: number };
  ui_hints?: {
    display_name?: string;
    group?: string;
    advanced?: boolean;
    control_type?: string;
  };
  uncertainty?: { distribution?: string; std_dev?: number };
  provenance?: string;
}

/** /mission-plan/waypoints response */
export interface WaypointsResponse {
  waypoints: WaypointDTO[];
  analysis: MissionAnalysis | null;
}

export interface WaypointDTO {
  latitude_deg: number;
  longitude_deg: number;
  altitude_m: number;
  speed_ms?: number;
  loiter_time_s?: number;
  camera_action?: string;
  order: number;
}

export interface MissionAnalysis {
  total_distance_m: number;
  total_distance_nmi: number;
  estimated_duration_s: number;
  estimated_duration_min: number;
  max_altitude_m: number;
  min_altitude_m: number;
  waypoint_count: number;
  avg_speed_ms: number;
  leg_distances_m: number[];
}

/** POST /mission-plan/validate */
export interface MissionValidateRequest {
  twin_id: string;
  twin_params: Record<string, unknown>;
  environment?: Record<string, unknown> | null;
  geofence?: [number, number][] | null;
  terrain_elevations_m?: number[] | null;
  required_payload_kg?: number | null;
  target_size_m?: number | null;
  min_pixels_on_target?: number | null;
  max_gsd_cm_px?: number | null;
  exposure_time_s?: number | null;
  max_blur_px?: number | null;
  min_overlap_pct?: number | null;
  trigger_interval_m?: number | null;
}

export interface MissionValidateCheck {
  name: string;
  passed: boolean;
  value: number;
  limit: number;
  unit: string;
  detail: string;
}

export interface MissionValidateResponse {
  is_valid: boolean;
  checks: MissionValidateCheck[];
  warnings: string[];
}

/** /environment responses */
export interface SolarResponse {
  elevation_deg: number;
  azimuth_deg: number;
  zenith_deg: number;
  declination_deg: number;
  sunrise_hour: number;
  sunset_hour: number;
  day_length_hr: number;
  ghi_w_m2: number;
  dni_w_m2: number;
  dhi_w_m2: number;
  illuminance_lux: number;
  solar_noon_utc: string;
  is_daytime: boolean;
}

export interface WindLayer {
  height_m: number;
  speed_ms: number;
  direction_deg: number;
  gusts_ms: number;
}

export interface WeatherResponse {
  temperature_c: number;
  pressure_hpa: number;
  humidity_pct: number;
  cloud_cover_pct: number;
  visibility_m: number;
  precipitation_mm: number;
  density_altitude_ft: number;
  air_density_kgm3: number;
  flight_category: string;
  conditions_summary: string;
  timestamp: string;
  wind_layers: WindLayer[];
}

export interface TerrainResponse {
  latitude: number;
  longitude: number;
  elevation_m: number;
  elevation_ft: number;
}

export interface TerrainProfileResponse {
  points: Array<{ latitude: number; longitude: number; elevation_m: number }>;
  min_elevation_m: number;
  max_elevation_m: number;
  mean_elevation_m: number;
  elevation_range_m: number;
}

export interface NiirsLevel {
  level: number;
  category: string;
  description: string;
  tasks: string[];
  min_gsd_cm?: number;
  typical_altitude_m?: number;
}

export interface ModelChainResponse {
  speed_ms: number;
  altitude_m: number;
  stages: Record<string, Record<string, number>>;
  niirs_interpretation: {
    level: number;
    category: string;
    description: string;
    tasks: string[];
  };
}

/** /telemetry responses */
export type TelemetryLinkProfile = 'default' | 'low_bandwidth';

export interface TelemetryStatus {
  connected: boolean;
  address?: string;
  system_id?: number;
  link_profile?: TelemetryLinkProfile;
  connection?: {
    address: string;
    link_profile: TelemetryLinkProfile;
    uptime_s: number;
    messages_received: number;
  };
}

export interface TelemetrySnapshot {
  timestamp: number;
  connection: {
    connected: boolean;
    address: string;
    link_profile: TelemetryLinkProfile;
    uptime_s: number;
    messages_received: number;
  };
  position: { latitude_deg: number; longitude_deg: number; absolute_altitude_m: number; relative_altitude_m: number };
  attitude: { roll_deg: number; pitch_deg: number; yaw_deg: number };
  velocity: { groundspeed_ms: number; airspeed_ms: number; climb_rate_ms: number; velocity_north_ms: number; velocity_east_ms: number; velocity_down_ms: number };
  battery: { voltage_v: number; current_a: number; remaining_pct: number; temperature_c: number | null };
  gps: { fix_type: string; num_satellites: number; hdop: number };
  wind: { speed_ms: number; direction_deg: number };
  status: { flight_mode: string; armed: boolean; in_air: boolean; health_ok: boolean };
}

export interface ParamMapping {
  twin_subsystem: string;
  twin_param: string;
  px4_param: string;
  px4_description: string;
  px4_group: string;
  px4_unit: string;
}

/** /calibration responses */
export interface CalibrationStatus {
  twin_id: string;
  calibration_runs: number;
  last_calibrated?: string;
  soh_pct?: number;
}

/** /catalog responses */
export interface CatalogEntry {
  id: string;
  subsystem_type: string;
  manufacturer: string;
  model_name: string;
  description: string;
  parameters: Record<string, unknown>;
  datasheet_url?: string;
}

/** /execution responses */
export interface MissionUploadResponse {
  success: boolean;
  message: string;
  items_uploaded: number;
}

/** /mission-plan upload/download responses */
export interface DroneTransferResponse {
  success: boolean;
  waypoints_uploaded?: number;
  waypoints_downloaded?: number;
  error?: string;
}

export interface LogUploadResponse {
  filename: string;
  format: string;
  record_count: number;
  topics: string[];
  metadata: Record<string, unknown>;
  timeseries?: Record<string, unknown>;
  summary?: Record<string, unknown>;
}
