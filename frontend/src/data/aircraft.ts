/**
 * Hardcoded aircraft fleet presets.
 *
 * Engine data sourced from Cobra AeroSystems datasheets (A33N, A33HF, A99S, A99HF).
 * Airframe data sourced from VA-55, VA-120, VA-150 datasheets.
 *
 * Engine data verified against Cobra datasheets (April 2025 revision).
 * Airframe data verified against VA-series datasheets (Nov 2025 revision).
 * Fuel capacity and consumption rates not in datasheets — marked as estimated.
 *
 * PROVENANCE: Every numeric parameter tracks its source via the
 * `estimated_parameters` and `engine_estimated_parameters` lists on
 * each preset.  The validation engine uses these to flag outputs that
 * depend on non-datasheet values.
 */

export type FuelType = 'gasoline' | 'heavy_fuel' | 'electric' | 'hybrid_hf' | 'hybrid_gasoline';
export type PropulsionArch = 'electric' | 'direct_ice' | 'series_hybrid';
export type AircraftType = 'multirotor' | 'fixed_wing' | 'vtol_fw' | 'vtol_mr';

export type ParamSource = 'datasheet' | 'estimated' | 'derived';

export interface CameraPreset {
  name: string;
  sensor_width_mm: number;
  sensor_height_mm: number;
  focal_length_mm: number;
  pixels_h: number;
  pixels_v: number;
  /** Aperture f-number for motion blur estimation */
  aperture: number;
}

export interface EngineSpec {
  model: string;
  displacement_cc: number;
  cylinders: number;
  power_kw: number;
  power_hp: number;
  rpm_max: number;
  weight_kg: number;
  fuel_type: FuelType;
  bsfc_g_per_kwhr: number;
}

export interface AircraftPreset {
  id: string;
  name: string;
  short_name: string;
  type: AircraftType;
  propulsion_arch: PropulsionArch;
  engine: EngineSpec;

  // Physical
  mtow_kg: number;
  airframe_mass_kg: number;
  payload_max_kg: number;

  // Performance
  endurance_min: number;          // at nominal payload, ISA SL
  endurance_min_max_fuel: number; // at zero payload
  range_km: number;
  max_speed_ms: number;
  cruise_speed_ms: number;
  max_altitude_m_asl: number;
  wind_limit_ms: number;
  operating_temp_min_c: number;
  operating_temp_max_c: number;

  // Fuel / energy
  fuel_type: FuelType;
  fuel_capacity_l: number;
  fuel_consumption_l_per_hr: number;

  // Dimensions
  frame_width_m: number;
  frame_height_m: number;

  // Default payload / optics
  default_camera: CameraPreset;

  // Meta
  datasheet_path: string;
  description: string;
  roles: string[];

  /**
   * Parameters on this aircraft preset that are ESTIMATED (not from datasheets).
   * The validation engine must flag any mission output that depends on these.
   */
  estimated_parameters: string[];

  /**
   * Parameters on the engine that are ESTIMATED (not from datasheets).
   */
  engine_estimated_parameters: string[];
}

// ─── ENGINE SPECS (from Cobra AeroSystems datasheets) ──────────────────────

const ENGINE_A33N: EngineSpec = {
  model: 'Cobra A33N',
  displacement_cc: 33,
  cylinders: 1,
  power_kw: 2.2,
  power_hp: 2.9,
  rpm_max: 8350,
  weight_kg: 3.15,   // includes engine, exhaust, ECU, fuel pump, harnesses
  fuel_type: 'gasoline',
  bsfc_g_per_kwhr: 500,  // 0.82 lb/hp-hr
};

const ENGINE_A33HF: EngineSpec = {
  model: 'Cobra A33HF',
  displacement_cc: 33,
  cylinders: 1,
  power_kw: 1.9,
  power_hp: 2.5,
  rpm_max: 8050,
  weight_kg: 3.15,
  fuel_type: 'heavy_fuel',   // JP5, JP8, Jet-A compatible
  bsfc_g_per_kwhr: 500,      // 0.83 lb/hp-hr
};

const ENGINE_A99S: EngineSpec = {
  model: 'Cobra A99S',
  displacement_cc: 99,
  cylinders: 3,              // triple inline, fires every 120°
  power_kw: 7.0,             // estimated shaft power; generator output 4.8 kW DC rectified
  power_hp: 9.4,             // estimated from shaft power
  rpm_max: 7000,             // estimated from A99HF peak-power RPM
  weight_kg: 5.58,           // includes engine, exhaust, ECU, fuel pump, injectors, ignition, generator, harnesses
  fuel_type: 'gasoline',
  bsfc_g_per_kwhr: 460,      // 0.76 lb/hp-hr cruise
};

const ENGINE_A99HF: EngineSpec = {
  model: 'Cobra A99HF',
  displacement_cc: 101.4,
  cylinders: 3,
  power_kw: 6.5,             // at 7000 RPM
  power_hp: 8.7,
  rpm_max: 7000,
  weight_kg: 8.4,            // includes engine, exhaust, ECU, fuel system, ignition, generator, harnesses, cooling
  fuel_type: 'heavy_fuel',   // JP5, JP8, Jet-A compatible
  bsfc_g_per_kwhr: 460,      // 0.76 lb/hp-hr cruise
};

// ─── DEFAULT CAMERA PRESETS ────────────────────────────────────────────────

/** Sony A7R IV class — high-resolution mapping / inspection */
const CAMERA_HR_MAPPING: CameraPreset = {
  name: 'Sony A7R IV (61MP)',
  sensor_width_mm: 35.7,
  sensor_height_mm: 23.8,
  focal_length_mm: 35,
  pixels_h: 9504,
  pixels_v: 6336,
  aperture: 4.0,
};

/** Sony RX1R II class — compact full-frame inspection */
const CAMERA_COMPACT_FF: CameraPreset = {
  name: 'Sony RX1R II (42MP)',
  sensor_width_mm: 35.9,
  sensor_height_mm: 24.0,
  focal_length_mm: 35,
  pixels_h: 7952,
  pixels_v: 5304,
  aperture: 2.8,
};

/** DJI Zenmuse P1 class — photogrammetry payload */
const CAMERA_ZENMUSE_P1: CameraPreset = {
  name: 'Zenmuse P1 (45MP)',
  sensor_width_mm: 35.9,
  sensor_height_mm: 24.0,
  focal_length_mm: 35,
  pixels_h: 8192,
  pixels_v: 5460,
  aperture: 4.0,
};

// ─── AIRCRAFT FLEET ────────────────────────────────────────────────────────

export const AIRCRAFT_FLEET: AircraftPreset[] = [
  {
    id: 'va55_a33hf',
    name: 'VA-55 / A33HF',
    short_name: 'VA-55',
    type: 'multirotor',
    propulsion_arch: 'direct_ice',
    engine: ENGINE_A33HF,

    mtow_kg: 24.95,             // 55 lbs gross weight
    airframe_mass_kg: 16.78,    // 37 lbs empty weight
    payload_max_kg: 5.45,       // nose 4.54 kg + booms 0.91 kg

    endurance_min: 360,          // 6 hrs at nominal payload
    endurance_min_max_fuel: 600, // 10 hrs max endurance
    range_km: 666,               // 360 nmi
    max_speed_ms: 30.9,          // 60 kts
    cruise_speed_ms: 18.5,       // 36 kts
    max_altitude_m_asl: 3658,    // 12,000 ft service ceiling (density altitude)
    wind_limit_ms: 15.4,         // 30 kts max crosswind
    operating_temp_min_c: -29,   // -20°F
    operating_temp_max_c: 49,    // 120°F

    fuel_type: 'heavy_fuel',
    fuel_capacity_l: 6.0,        // estimated — not in datasheet
    fuel_consumption_l_per_hr: 3.2, // estimated — not in datasheet

    frame_width_m: 3.96,         // 13.0 ft wingspan
    frame_height_m: 0.33,        // 1.08 ft height

    default_camera: CAMERA_COMPACT_FF,

    datasheet_path: '/A33HF_Data_Sheet.pdf',
    description:
      'Medium-lift multirotor with Cobra A33HF heavy-fuel engine. ' +
      'JP5/JP8/Jet-A compatible for logistics-supported operations. ' +
      'Ideal for infrastructure inspection at 30–80 m AGL.',
    roles: ['inspection', 'surveillance', 'mapping'],

    estimated_parameters: ['fuel_capacity_l', 'fuel_consumption_l_per_hr'],
    engine_estimated_parameters: [],
  },

  {
    id: 'va55_a33n',
    name: 'VA-55 / A33N',
    short_name: 'VA-55 (gasoline)',
    type: 'multirotor',
    propulsion_arch: 'direct_ice',
    engine: ENGINE_A33N,

    mtow_kg: 24.95,             // 55 lbs gross weight
    airframe_mass_kg: 16.78,    // 37 lbs empty weight
    payload_max_kg: 5.45,       // nose 4.54 kg + booms 0.91 kg

    endurance_min: 360,          // 6 hrs at nominal payload
    endurance_min_max_fuel: 600, // 10 hrs max endurance
    range_km: 666,               // 360 nmi
    max_speed_ms: 30.9,          // 60 kts
    cruise_speed_ms: 18.5,       // 36 kts
    max_altitude_m_asl: 3658,    // 12,000 ft service ceiling (density altitude)
    wind_limit_ms: 15.4,         // 30 kts max crosswind
    operating_temp_min_c: -29,   // -20°F
    operating_temp_max_c: 49,    // 120°F

    fuel_type: 'gasoline',
    fuel_capacity_l: 5.5,        // estimated — not in datasheet
    fuel_consumption_l_per_hr: 3.0, // estimated — not in datasheet

    frame_width_m: 3.96,         // 13.0 ft wingspan
    frame_height_m: 0.33,        // 1.08 ft height

    default_camera: CAMERA_COMPACT_FF,

    datasheet_path: '/A33N_Data_Sheet.pdf',
    description:
      'Medium-lift multirotor with Cobra A33N gasoline engine. ' +
      'Cost-effective platform for commercial inspections and mapping.',
    roles: ['inspection', 'mapping'],

    estimated_parameters: ['fuel_capacity_l', 'fuel_consumption_l_per_hr'],
    engine_estimated_parameters: [],
  },

  {
    id: 'va120_a99hf',
    name: 'VA-120 / A99HF',
    short_name: 'VA-120',
    type: 'multirotor',
    propulsion_arch: 'series_hybrid',
    engine: ENGINE_A99HF,

    mtow_kg: 68.0,              // 150 lbs gross weight
    airframe_mass_kg: 34.0,     // 75 lbs empty weight
    payload_max_kg: 15.83,      // nose 11.3 kg + booms 4.53 kg

    endurance_min: 480,          // 8 hrs at nominal payload
    endurance_min_max_fuel: 960, // 16 hrs max endurance
    range_km: 1500,              // 810 nmi
    max_speed_ms: 33.4,          // 65 kts
    cruise_speed_ms: 21.6,       // 42 kts
    max_altitude_m_asl: 5486,    // 18,000 ft service ceiling (density altitude)
    wind_limit_ms: 15.4,         // 30 kts max crosswind
    operating_temp_min_c: -29,   // -20°F
    operating_temp_max_c: 49,    // 120°F

    fuel_type: 'heavy_fuel',
    fuel_capacity_l: 14.0,       // estimated — not in datasheet
    fuel_consumption_l_per_hr: 6.5, // estimated — not in datasheet

    frame_width_m: 4.88,         // 16.0 ft wingspan
    frame_height_m: 0.66,        // 2.17 ft height

    default_camera: CAMERA_HR_MAPPING,

    datasheet_path: '/VA-120+Datasheet+v1.pdf',
    description:
      'Heavy-lift series-hybrid multirotor with Cobra A99HF heavy-fuel ' +
      'generator. Extended endurance with high payload capacity. ' +
      'Suitable for large-area mapping, multi-sensor inspection, and ISR.',
    roles: ['inspection', 'mapping', 'isr', 'delivery'],

    estimated_parameters: ['fuel_capacity_l', 'fuel_consumption_l_per_hr'],
    engine_estimated_parameters: [],
  },

  {
    id: 'va150_a99s',
    name: 'VA-150 / A99S',
    short_name: 'VA-150',
    type: 'multirotor',
    propulsion_arch: 'series_hybrid',
    engine: ENGINE_A99S,

    mtow_kg: 68.0,              // 150 lbs gross weight
    airframe_mass_kg: 34.0,     // 75 lbs empty weight
    payload_max_kg: 15.83,      // nose 11.3 kg + booms 4.53 kg

    endurance_min: 480,          // 8 hrs at nominal payload
    endurance_min_max_fuel: 960, // 16 hrs max endurance
    range_km: 1500,              // 810 nmi
    max_speed_ms: 33.4,          // 65 kts
    cruise_speed_ms: 21.6,       // 42 kts
    max_altitude_m_asl: 5486,    // 18,000 ft service ceiling (density altitude)
    wind_limit_ms: 15.4,         // 30 kts max crosswind
    operating_temp_min_c: -29,   // -20°F
    operating_temp_max_c: 49,    // 120°F

    fuel_type: 'gasoline',
    fuel_capacity_l: 18.0,       // estimated — not in datasheet
    fuel_consumption_l_per_hr: 7.0, // estimated — not in datasheet

    frame_width_m: 4.88,         // 16.0 ft wingspan
    frame_height_m: 0.66,        // 2.17 ft height

    default_camera: CAMERA_ZENMUSE_P1,

    datasheet_path: '/VA-150+Datasheet+v5.pdf',
    description:
      'Max-lift series-hybrid multirotor with Cobra A99S generator. ' +
      'Highest payload and endurance in the fleet. ' +
      'Multi-mission platform for heavy sensor suites and delivery.',
    roles: ['inspection', 'mapping', 'isr', 'delivery', 'sar'],

    estimated_parameters: ['fuel_capacity_l', 'fuel_consumption_l_per_hr'],
    engine_estimated_parameters: ['power_kw', 'power_hp', 'rpm_max'],
  },
];

export const AIRCRAFT_BY_ID = Object.fromEntries(
  AIRCRAFT_FLEET.map((a) => [a.id, a]),
) as Record<string, AircraftPreset>;

/**
 * Backend ``/twins/{id}/...`` routes expect a **persisted** vehicle twin id or the
 * literal ``default``. Fleet preset keys (e.g. ``va55_a33hf``) are **frontend-only**
 * and are not rows in Postgres — sending them causes 404 ``Twin not found``.
 */
export function backendTwinIdFromFleetSelection(selectedId: string | null): string {
  if (!selectedId) return 'default';
  if (selectedId in AIRCRAFT_BY_ID) return 'default';
  return selectedId;
}
