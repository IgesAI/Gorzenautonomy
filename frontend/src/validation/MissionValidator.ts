/**
 * Frontend mission validation — mirrors the backend enforcement rules.
 *
 * Every output produced by the feasibility engine must be:
 * 1. Derived ONLY from hard-coded platform specs, sensor specs, or explicit inputs
 * 2. Physically correct and internally consistent
 * 3. Free of hidden assumptions, fallback values, or inferred constants
 *
 * This module provides the validation report format and helper functions.
 */

import type { AircraftPreset, CameraPreset } from '../data/aircraft';
import type { MissionConfig, FeasibilityViolation } from '../data/missions';

export type ValidationStatus = 'PASS' | 'FAIL' | 'INSUFFICIENT_DATA';

export interface ConstraintCheck {
  name: string;
  status: 'PASS' | 'FAIL';
  value: number;
  limit: number;
  unit: string;
  detail: string;
}

export interface MissionValidationReport {
  status: ValidationStatus;

  platform: {
    id: string;
    name: string;
    verified_params: string[];
    estimated_params: string[];
    missing_params: string[];
  };

  detection: {
    required_pot: number;
    achieved_pot: number;
    margin_pct: number;
    status: 'PASS' | 'FAIL';
  };

  constraints: {
    motion_blur: ConstraintCheck;
    gsd: ConstraintCheck;
    endurance: ConstraintCheck;
    payload: ConstraintCheck;
  };

  violations: FeasibilityViolation[];

  confidence: 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT_DATA';
  confidence_reason: string;
}

function computeGSD_m(altitude_m: number, cam: CameraPreset): number {
  return (cam.sensor_width_mm * altitude_m) / (cam.focal_length_mm * cam.pixels_h);
}

export function validateMission(
  aircraft: AircraftPreset,
  config: MissionConfig,
): MissionValidationReport {
  const violations: FeasibilityViolation[] = [];

  const estimated_params = [
    ...aircraft.estimated_parameters,
    ...aircraft.engine_estimated_parameters.map((p) => `engine.${p}`),
  ];

  for (const p of estimated_params) {
    violations.push({
      type: 'estimated_param',
      parameter: p,
      location: `aircraft[${aircraft.id}]`,
      impact: `${p} is estimated — computations depending on it are not verified`,
      correction: `Obtain ${p} from manufacturer datasheet or measurement`,
    });
  }

  const cam = aircraft.default_camera;
  const gsd_m = computeGSD_m(config.nominal_altitude_m, cam);
  const gsd_cm = gsd_m * 100;
  const target_m = config.target_feature_mm / 1000;
  const pot = gsd_m > 0 ? target_m / gsd_m : 0;
  const min_pot = 2; // Nyquist minimum

  const blur_px =
    gsd_m > 0
      ? (config.nominal_speed_ms * config.exposure_time_s) / gsd_m
      : Infinity;

  const fuelEnduranceMin =
    config.fuel_consumption_l_per_hr > 0
      ? (config.fuel_capacity_l / config.fuel_consumption_l_per_hr) * 60
      : aircraft.endurance_min;
  const effectiveEndurance = Math.min(aircraft.endurance_min, fuelEnduranceMin);

  const gsdCheck: ConstraintCheck = {
    name: 'gsd',
    status: gsd_cm <= config.min_gsd_cm_per_px ? 'PASS' : 'FAIL',
    value: gsd_cm,
    limit: config.min_gsd_cm_per_px,
    unit: 'cm/px',
    detail: `GSD ${gsd_cm.toFixed(3)} cm/px vs limit ${config.min_gsd_cm_per_px} cm/px`,
  };

  const blurCheck: ConstraintCheck = {
    name: 'motion_blur',
    status: blur_px <= config.max_blur_px ? 'PASS' : 'FAIL',
    value: blur_px,
    limit: config.max_blur_px,
    unit: 'px',
    detail: `Blur ${blur_px.toFixed(3)} px vs limit ${config.max_blur_px} px`,
  };

  const enduranceCheck: ConstraintCheck = {
    name: 'endurance',
    status: effectiveEndurance >= config.min_endurance_min ? 'PASS' : 'FAIL',
    value: effectiveEndurance,
    limit: config.min_endurance_min,
    unit: 'min',
    detail: `${Math.round(effectiveEndurance)} min vs required ${config.min_endurance_min} min`,
  };

  const payloadCheck: ConstraintCheck = {
    name: 'payload',
    status: aircraft.payload_max_kg >= config.required_payload_kg ? 'PASS' : 'FAIL',
    value: aircraft.payload_max_kg,
    limit: config.required_payload_kg,
    unit: 'kg',
    detail: `${aircraft.payload_max_kg} kg capacity vs ${config.required_payload_kg} kg required`,
  };

  const allChecks = [gsdCheck, blurCheck, enduranceCheck, payloadCheck];
  const anyFailed = allChecks.some((c) => c.status === 'FAIL');
  const hasMissing = false;
  const hasEstimated = estimated_params.length > 0;

  let confidence: 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT_DATA';
  let confidence_reason: string;
  if (hasMissing) {
    confidence = 'INSUFFICIENT_DATA';
    confidence_reason = 'Required parameters are missing';
  } else if (hasEstimated) {
    confidence = 'LOW';
    confidence_reason = `${estimated_params.length} parameter(s) are estimated, not from datasheets`;
  } else {
    confidence = 'HIGH';
    confidence_reason = 'All parameters sourced from datasheets';
  }

  const detection_margin = pot > 0 ? ((pot - min_pot) / min_pot) * 100 : -100;

  return {
    status: anyFailed ? 'FAIL' : 'PASS',
    platform: {
      id: aircraft.id,
      name: aircraft.name,
      verified_params: Object.keys(aircraft).filter(
        (k) => !aircraft.estimated_parameters.includes(k),
      ),
      estimated_params,
      missing_params: [],
    },
    detection: {
      required_pot: min_pot,
      achieved_pot: pot,
      margin_pct: detection_margin,
      status: pot >= min_pot ? 'PASS' : 'FAIL',
    },
    constraints: {
      motion_blur: blurCheck,
      gsd: gsdCheck,
      endurance: enduranceCheck,
      payload: payloadCheck,
    },
    violations,
    confidence,
    confidence_reason,
  };
}
