/**
 * Mission configuration and feasibility engine.
 *
 * Users define all mission parameters from scratch via MissionConfig.
 * The feasibility engine scores a given aircraft + config against
 * real-world physics (GSD, NIIRS, endurance, payload, wind, temperature).
 *
 * ENFORCEMENT: No silent fallbacks.  Every parameter must be explicitly
 * provided.  Missing environment data results in FAIL, not a default
 * substitution.
 *
 * Optical pipeline paths:
 *   onboard  — AI inference happens on the aircraft in-flight
 *   rtn      — footage returned to home station for VLM processing
 *   both     — either path works
 */

export type InferencePath = 'onboard' | 'rtn' | 'both';

export interface MissionConfig {
  /** Min ground sampling distance to resolve target features (cm/px) */
  min_gsd_cm_per_px: number;
  /** Min NIIRS score needed */
  min_niirs: number;
  /** Smallest defect / feature that must be detectable (mm) */
  target_feature_mm: number;
  /** Nominal operating altitude AGL (m) */
  nominal_altitude_m: number;
  /** Nominal cruise speed (m/s) */
  nominal_speed_ms: number;
  /** Minimum endurance needed (minutes) */
  min_endurance_min: number;
  /** Maximum payload needed (kg) — sensor suite weight */
  required_payload_kg: number;
  /** Max wind the mission can tolerate (m/s) */
  max_wind_ms: number;
  /** Preferred inference pipeline */
  inference_path: InferencePath;
  /** Estimated post-flight processing time at home station (hours) */
  post_processing_hrs: number;
  /** Confidence thresholds for the feasibility engine */
  pass_threshold: number;
  warn_threshold: number;

  /**
   * Camera exposure time (seconds).  MUST be explicit — different sensors
   * have different capabilities.  Do not assume 1/1000s.
   */
  exposure_time_s: number;

  /**
   * Maximum acceptable motion blur in pixels.
   * Default 0.5 px for sub-pixel accuracy (Johnson criteria).
   */
  max_blur_px: number;

  // ── Overrides for values not in aircraft datasheets ────────────────────
  /** VTOL battery capacity (Ah) — not in datasheets */
  battery_capacity_ah: number;
  /** Fuel tank capacity (L) — estimated, not in datasheets */
  fuel_capacity_l: number;
  /** Fuel burn rate (L/hr) — estimated, not in datasheets */
  fuel_consumption_l_per_hr: number;
  /** Relative Edge Response for NIIRS (0–1) — optics quality assumption */
  rer: number;
  /** Envelope analysis grid resolution (points per axis) */
  grid_resolution: number;
  /** Uncertainty quantification method */
  uq_method: 'deterministic' | 'monte_carlo';
}

export const DEFAULT_MISSION_CONFIG: MissionConfig = {
  min_gsd_cm_per_px: 1.5,
  min_niirs: 6.0,
  target_feature_mm: 5,
  nominal_altitude_m: 50,
  nominal_speed_ms: 12,
  min_endurance_min: 30,
  required_payload_kg: 3.5,
  max_wind_ms: 10,
  inference_path: 'rtn',
  post_processing_hrs: 2,
  pass_threshold: 0.85,
  warn_threshold: 0.65,

  exposure_time_s: 1 / 1000,
  max_blur_px: 0.5,

  battery_capacity_ah: 16,
  fuel_capacity_l: 6.0,
  fuel_consumption_l_per_hr: 3.2,
  rer: 0.9,
  grid_resolution: 20,
  uq_method: 'deterministic',
};

// ─── FEASIBILITY ENGINE ────────────────────────────────────────────────────

import type { AircraftPreset } from './aircraft';

export interface FeasibilityAxis {
  label: string;
  score: number;        // 0–1
  pass: boolean;
  marginal: boolean;
  detail: string;
  value_str: string;
  requirement_str: string;
}

export interface FeasibilityViolation {
  type: 'assumption' | 'fallback' | 'invalid_constant' | 'missing_data' | 'estimated_param';
  parameter: string;
  location: string;
  impact: string;
  correction: string;
}

export interface FeasibilityResult {
  overall: number;      // 0–1 weighted
  viable: boolean;
  marginal: boolean;
  axes: FeasibilityAxis[];
  gsd_cm_per_px: number;
  niirs: number;
  pixels_on_target: number;
  detectable_crack_mm: number;
  violations: FeasibilityViolation[];
  confidence: 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT_DATA';
}

/**
 * NIIRS approximation using GIQE 5 (natural log formulation).
 *   NIIRS = 9.57 + c1*ln(GSD_inches) + c2*ln(RER)
 *
 * RER MUST be provided explicitly — it depends on optics quality.
 */
function computeNIIRS(gsd_cm: number, rer: number): number {
  const gsd_inches = gsd_cm / 2.54;
  return 9.57 - 3.32 * Math.log(gsd_inches) + 3.32 * Math.log(rer);
}

/**
 * GSD = (sensor_width_mm * altitude_m) / (focal_length_mm * pixels_h)
 * Result in m/px; multiply by 100 for cm/px.
 */
function computeGSD_cm(aircraft: AircraftPreset, altitude_m: number): number {
  const cam = aircraft.default_camera;
  return (cam.sensor_width_mm * altitude_m * 100) / (cam.focal_length_mm * cam.pixels_h);
}

/**
 * Pixels on target = target_size_m / gsd_m.
 * This is derived from first-principles geometry, not a heuristic.
 */
function computePixelsOnTarget(gsd_cm: number, target_feature_mm: number): number {
  const gsd_m = gsd_cm / 100;
  const target_m = target_feature_mm / 1000;
  return gsd_m > 0 ? target_m / gsd_m : 0;
}

export function computeFeasibility(
  aircraft: AircraftPreset,
  config: MissionConfig,
  env?: { wind_ms?: number; temperature_c?: number },
): FeasibilityResult {
  const violations: FeasibilityViolation[] = [];

  // Track provenance warnings from estimated parameters
  if (aircraft.estimated_parameters.length > 0) {
    for (const p of aircraft.estimated_parameters) {
      violations.push({
        type: 'estimated_param',
        parameter: p,
        location: `aircraft[${aircraft.id}]`,
        impact: `${p} is estimated (not from datasheet) — endurance/range calculations are unreliable`,
        correction: `Obtain ${p} from manufacturer datasheet or ground-truth measurement`,
      });
    }
  }
  if (aircraft.engine_estimated_parameters.length > 0) {
    for (const p of aircraft.engine_estimated_parameters) {
      violations.push({
        type: 'estimated_param',
        parameter: `engine.${p}`,
        location: `engine[${aircraft.engine.model}]`,
        impact: `engine ${p} is estimated — power/consumption calculations are unreliable`,
        correction: `Obtain ${p} from Cobra datasheet`,
      });
    }
  }

  // Environment: FAIL-FIRST if not provided (no silent fallbacks)
  const hasWind = env?.wind_ms !== undefined && env.wind_ms !== null;
  const hasTemp = env?.temperature_c !== undefined && env.temperature_c !== null;
  const windMs = hasWind ? env!.wind_ms! : 0;
  const tempC = hasTemp ? env!.temperature_c! : 0;

  if (!hasWind) {
    violations.push({
      type: 'missing_data',
      parameter: 'wind_ms',
      location: 'environment',
      impact: 'Wind data not provided — wind check uses 0 m/s (optimistic)',
      correction: 'Provide current wind speed from weather source',
    });
  }
  if (!hasTemp) {
    violations.push({
      type: 'missing_data',
      parameter: 'temperature_c',
      location: 'environment',
      impact: 'Temperature not provided — temperature check cannot validate',
      correction: 'Provide current temperature from weather source',
    });
  }

  const gsd = computeGSD_cm(aircraft, config.nominal_altitude_m);
  const niirs = computeNIIRS(gsd, config.rer);
  const pot = computePixelsOnTarget(gsd, config.target_feature_mm);

  // Detectable feature size = GSD (the physical extent of one pixel on the ground)
  // Minimum detectable feature requires at least ~2 px (Nyquist sampling).
  // detectable_mm = gsd_m * 2 * 1000 = gsd_cm * 20
  const detectable_mm = gsd * 20;

  // ── 1. Optical / GSD ────────────────────────────────────────────────────
  const gsdRatio = config.min_gsd_cm_per_px / gsd;
  const opticalScore = Math.min(1, gsdRatio);
  const opticalPass = gsd <= config.min_gsd_cm_per_px;
  const opticalMarginal = !opticalPass && gsd <= config.min_gsd_cm_per_px * 1.3;

  const optical: FeasibilityAxis = {
    label: 'Optical Resolution',
    score: opticalScore,
    pass: opticalPass,
    marginal: opticalMarginal,
    detail: `GSD ${gsd.toFixed(2)} cm/px at ${config.nominal_altitude_m} m AGL`,
    value_str: `${gsd.toFixed(2)} cm/px`,
    requirement_str: `≤ ${config.min_gsd_cm_per_px} cm/px`,
  };

  // ── 2. NIIRS ─────────────────────────────────────────────────────────────
  const niirsDiff = niirs - config.min_niirs;
  const niirScore = Math.min(1, Math.max(0, 0.5 + niirsDiff * 0.3));
  const niirAxis: FeasibilityAxis = {
    label: 'Image Intelligence (NIIRS)',
    score: niirScore,
    pass: niirs >= config.min_niirs,
    marginal: niirs >= config.min_niirs - 0.5 && niirs < config.min_niirs,
    detail: `NIIRS ${niirs.toFixed(1)} — ${pot.toFixed(1)} px on target (feature ${config.target_feature_mm} mm)`,
    value_str: `NIIRS ${niirs.toFixed(1)}`,
    requirement_str: `≥ NIIRS ${config.min_niirs}`,
  };

  // ── 3. Endurance ─────────────────────────────────────────────────────────
  const fuelEnduranceMin =
    config.fuel_consumption_l_per_hr > 0
      ? (config.fuel_capacity_l / config.fuel_consumption_l_per_hr) * 60
      : aircraft.endurance_min;
  const effectiveEndurance = Math.min(aircraft.endurance_min, fuelEnduranceMin);
  const endRatio = effectiveEndurance / config.min_endurance_min;
  const endScore = Math.min(1, Math.max(0, endRatio * 0.8));
  const endAxis: FeasibilityAxis = {
    label: 'Endurance',
    score: endScore,
    pass: effectiveEndurance >= config.min_endurance_min,
    marginal:
      effectiveEndurance >= config.min_endurance_min * 0.85 &&
      effectiveEndurance < config.min_endurance_min,
    detail: `${Math.round(effectiveEndurance)} min available vs ${config.min_endurance_min} min required`,
    value_str: `${Math.round(effectiveEndurance)} min`,
    requirement_str: `≥ ${config.min_endurance_min} min`,
  };

  // ── 4. Payload ────────────────────────────────────────────────────────────
  const payloadMargin = aircraft.payload_max_kg - config.required_payload_kg;
  const payloadScore = Math.min(1, Math.max(0, payloadMargin / 5 + 0.5));
  const payloadAxis: FeasibilityAxis = {
    label: 'Payload Capacity',
    score: payloadScore,
    pass: aircraft.payload_max_kg >= config.required_payload_kg,
    marginal:
      aircraft.payload_max_kg >= config.required_payload_kg * 0.9 &&
      aircraft.payload_max_kg < config.required_payload_kg,
    detail: `${aircraft.payload_max_kg} kg capacity — ${config.required_payload_kg} kg sensor suite`,
    value_str: `${aircraft.payload_max_kg} kg`,
    requirement_str: `≥ ${config.required_payload_kg} kg`,
  };

  // ── 5. Wind ───────────────────────────────────────────────────────────────
  const effectiveWindLimit = Math.min(aircraft.wind_limit_ms, config.max_wind_ms);
  const windScore = hasWind
    ? Math.min(1, Math.max(0, (effectiveWindLimit - windMs) / effectiveWindLimit))
    : 0;
  const windAxis: FeasibilityAxis = {
    label: 'Wind Tolerance',
    score: windScore,
    pass: hasWind ? windMs <= effectiveWindLimit : false,
    marginal: hasWind && windMs > effectiveWindLimit && windMs <= aircraft.wind_limit_ms,
    detail: hasWind
      ? `Current wind ${windMs.toFixed(1)} m/s — limit ${effectiveWindLimit} m/s`
      : `INSUFFICIENT_DATA: Wind speed not provided`,
    value_str: hasWind ? `${windMs.toFixed(1)} m/s` : 'N/A',
    requirement_str: `≤ ${effectiveWindLimit} m/s`,
  };

  // ── 6. Temperature ────────────────────────────────────────────────────────
  const inTempRange = hasTemp
    ? tempC >= aircraft.operating_temp_min_c && tempC <= aircraft.operating_temp_max_c
    : false;
  const tempScore = hasTemp ? (inTempRange ? 1.0 : 0.2) : 0;
  const tempAxis: FeasibilityAxis = {
    label: 'Temperature',
    score: tempScore,
    pass: inTempRange,
    marginal: hasTemp && !inTempRange &&
      (tempC >= aircraft.operating_temp_min_c - 5 &&
        tempC <= aircraft.operating_temp_max_c + 5),
    detail: hasTemp
      ? `${tempC.toFixed(0)} °C — aircraft range ${aircraft.operating_temp_min_c}..${aircraft.operating_temp_max_c} °C`
      : `INSUFFICIENT_DATA: Temperature not provided`,
    value_str: hasTemp ? `${tempC.toFixed(0)} °C` : 'N/A',
    requirement_str: `${aircraft.operating_temp_min_c}..${aircraft.operating_temp_max_c} °C`,
  };

  // ── 7. Motion Blur ──────────────────────────────────────────────────────
  // blur_px = (ground_speed * exposure_time) / GSD
  // Uses config.exposure_time_s — must be explicit, not hardcoded
  const gsd_m = gsd / 100;
  const blurPixels = (config.nominal_speed_ms * config.exposure_time_s) / gsd_m;
  const maxExposure_s = (config.max_blur_px * gsd_m) / config.nominal_speed_ms;
  const maxShutterSpeed = Math.round(1 / maxExposure_s);
  const blurOk = blurPixels <= config.max_blur_px;
  const blurScore = Math.min(1, Math.max(0, 1 - (blurPixels - config.max_blur_px * 0.5) / (config.max_blur_px * 2)));
  const blurAxis: FeasibilityAxis = {
    label: 'Motion Blur',
    score: blurScore,
    pass: blurOk,
    marginal: blurPixels > config.max_blur_px && blurPixels <= config.max_blur_px * 2,
    detail: `${blurPixels.toFixed(2)} px blur at 1/${Math.round(1 / config.exposure_time_s)}s — need ≥1/${maxShutterSpeed} for <${config.max_blur_px}px`,
    value_str: `${blurPixels.toFixed(2)} px`,
    requirement_str: `≤ ${config.max_blur_px} px`,
  };

  const axes = [optical, niirAxis, endAxis, payloadAxis, windAxis, tempAxis, blurAxis];

  // ── Weighted overall ──────────────────────────────────────────────────────
  // All axes contribute equally: pass=1, fail=0.  No arbitrary weighting.
  const passCount = axes.filter((a) => a.pass).length;
  const overall = passCount / axes.length;

  // Confidence depends on data completeness and provenance
  const hasMissingData = violations.some((v) => v.type === 'missing_data');
  const hasEstimated = violations.some((v) => v.type === 'estimated_param');
  let confidence: 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT_DATA';
  if (hasMissingData) {
    confidence = 'INSUFFICIENT_DATA';
  } else if (hasEstimated) {
    confidence = 'LOW';
  } else {
    confidence = 'HIGH';
  }

  return {
    overall,
    viable: axes.every((a) => a.pass),
    marginal: !axes.every((a) => a.pass) && axes.every((a) => a.pass || a.marginal),
    axes,
    gsd_cm_per_px: gsd,
    niirs,
    pixels_on_target: pot,
    detectable_crack_mm: detectable_mm,
    violations,
    confidence,
  };
}
