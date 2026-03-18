export interface TypedParameter<T = number> {
  value: T;
  units: string;
  default_value?: T;
  uncertainty?: UncertaintySpec;
  constraints?: ParameterConstraints;
  ui_hints?: UIHints;
  model_binding?: string;
}

export interface UncertaintySpec {
  distribution: string;
  params: Record<string, number>;
  bounds?: [number, number];
  correlation_group_id?: string;
}

export interface ParameterConstraints {
  min_value?: number;
  max_value?: number;
  allowed_values?: unknown[];
}

export interface UIHints {
  control_type: string;
  group: string;
  advanced: boolean;
  display_name?: string;
  tooltip?: string;
  step?: number;
  precision?: number;
}

export interface SubsystemConfig {
  [key: string]: TypedParameter;
}

export interface VehicleTwin {
  twin_id: string;
  name: string;
  description: string;
  version: { major: number; minor: number; patch: number };
  build_hash: string;
  airframe: SubsystemConfig;
  lift_propulsion: SubsystemConfig;
  cruise_propulsion: SubsystemConfig;
  energy: SubsystemConfig;
  avionics: SubsystemConfig;
  compute: SubsystemConfig;
  comms: SubsystemConfig;
  payload: SubsystemConfig;
  ai_model: SubsystemConfig;
  mission_profile: {
    environment: SubsystemConfig;
    constraints: SubsystemConfig;
    waypoints: unknown[];
    mission_type: string;
  };
  created_at: string;
  updated_at: string;
}

export interface CatalogEntry {
  entry_id: string;
  subsystem_type: string;
  manufacturer: string;
  model_name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export type SubsystemType =
  | 'airframe'
  | 'lift_propulsion'
  | 'cruise_propulsion'
  | 'fuel_system'
  | 'energy'
  | 'avionics'
  | 'compute'
  | 'comms'
  | 'payload'
  | 'ai_model'
  | 'mission_profile';

export const SUBSYSTEM_LABELS: Record<SubsystemType, string> = {
  airframe: 'Airframe',
  lift_propulsion: 'VTOL Lift Motors',
  cruise_propulsion: 'Engine / Cruise',
  fuel_system: 'Fuel System',
  energy: 'Battery / Electrical',
  avionics: 'Avionics',
  compute: 'Compute',
  comms: 'Communications',
  payload: 'Payload',
  ai_model: 'AI Models',
  mission_profile: 'Mission Profile',
};
