export interface EnvelopeOutput {
  mean: number;
  std: number;
  percentiles: Record<string, number>;
  units: string;
  top_contributors?: string[];
}

export interface SensitivityEntry {
  parameter_name: string;
  sobol_first_order?: number;
  sobol_total?: number;
  contribution_pct: number;
}

export interface EnvelopeSurface {
  x_label: string;
  y_label: string;
  z_label: string;
  x_values: number[];
  y_values: number[];
  z_mean: number[][];
  z_p5: number[][];
  z_p95: number[][];
  feasible_mask?: boolean[][];
}

export interface EnvelopeResponse {
  speed_altitude_feasibility?: EnvelopeSurface;
  safe_inspection_speed?: EnvelopeOutput;
  fuel_endurance?: EnvelopeOutput;
  battery_reserve?: EnvelopeOutput;
  fuel_flow_rate?: EnvelopeOutput;
  identification_confidence?: EnvelopeSurface;
  endurance_surface?: EnvelopeSurface;
  mission_completion_probability?: number;
  sensitivity: SensitivityEntry[];
  computation_time_s: number;
  warnings?: string[];
}

export interface EnvelopeRequest {
  twin_id: string;
  speed_range_ms: [number, number];
  altitude_range_m: [number, number];
  grid_resolution: number;
  uq_method: string;
  mc_samples: number;
}
