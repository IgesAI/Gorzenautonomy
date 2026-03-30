import { useState } from 'react';
import { BarChart3, AlertCircle, Activity, Clock } from 'lucide-react';
import { clsx } from 'clsx';
import { useComputeEnvelope } from '../../hooks/useEnvelope';
import { GlassPanel } from '../layout/GlassPanel';
import { EnvelopeChart } from '../visualization/EnvelopeChart';
import { IdentConfidence } from '../visualization/IdentConfidence';
import { BatteryReserve } from '../visualization/BatteryReserve';
import { FuelEndurance } from '../visualization/FuelEndurance';
import { SensitivityBars } from '../visualization/SensitivityBars';
import { MissionProb } from '../visualization/MissionProb';
import type { EnvelopeResponse } from '../../types/envelope';
import type { AircraftPreset } from '../../data/aircraft';
import type { MissionConfig } from '../../data/missions';

function buildOverridesFromPreset(
  aircraft: AircraftPreset,
  env?: { wind_ms?: number; temperature_c?: number },
  config?: MissionConfig | null,
): Record<string, Record<string, number | string>> {
  const ktsToMs = 0.514444;
  const maxSpeedKts = aircraft.max_speed_ms / ktsToMs;
  const cruiseSpeedKts = aircraft.cruise_speed_ms / ktsToMs;
  const ceilingFt = aircraft.max_altitude_m_asl * 3.281;
  const refArea = aircraft.frame_width_m * aircraft.frame_height_m * 0.35;

  const effectiveWindMs = Math.min(
    config?.max_wind_ms ?? aircraft.wind_limit_ms,
    aircraft.wind_limit_ms,
  );

  return {
    airframe: {
      mass_mtow_kg: aircraft.mtow_kg,
      mass_empty_kg: aircraft.airframe_mass_kg,
      wing_span_m: aircraft.frame_width_m,
      height_m: aircraft.frame_height_m,
      wing_area_m2: refArea,
      max_speed_kts: maxSpeedKts,
      cruise_speed_kts: cruiseSpeedKts,
      service_ceiling_ft: ceilingFt,
      payload_capacity_nose_kg: aircraft.payload_max_kg,
      max_operating_temp_c: aircraft.operating_temp_max_c,
      min_operating_temp_c: aircraft.operating_temp_min_c,
      max_crosswind_kts: effectiveWindMs / ktsToMs,
    },
    cruise_propulsion: {
      displacement_cc: aircraft.engine.displacement_cc,
      max_power_kw: aircraft.engine.power_kw,
      bsfc_cruise_g_kwh: aircraft.engine.bsfc_g_per_kwhr,
      max_power_rpm: aircraft.engine.rpm_max,
      engine_mass_kg: aircraft.engine.weight_kg,
    },
    fuel_system: {
      tank_capacity_l: config?.fuel_capacity_l ?? aircraft.fuel_capacity_l,
      fuel_type: aircraft.fuel_type,
    },
    energy: {
      capacity_ah: config?.battery_capacity_ah ?? 16,
    },
    payload: {
      sensor_width_mm: aircraft.default_camera.sensor_width_mm,
      sensor_height_mm: aircraft.default_camera.sensor_height_mm,
      focal_length_mm: aircraft.default_camera.focal_length_mm,
      pixel_width: aircraft.default_camera.pixels_h,
      pixel_height: aircraft.default_camera.pixels_v,
    },
    mission_profile: {
      temperature_c: env?.temperature_c ?? 15,
      wind_speed_ms: env?.wind_ms ?? 0,
      min_gsd_cm_px: config?.min_gsd_cm_per_px ?? 1.5,
      target_feature_mm: config?.target_feature_mm ?? 5.0,
      min_identification_confidence: config?.pass_threshold ?? 0.8,
    },
  };
}

interface AnalysisPanelProps {
  aircraft: AircraftPreset | null;
  missionConfig?: MissionConfig | null;
  envSnapshot?: { wind_ms?: number; temperature_c?: number };
}

export function AnalysisPanel({ aircraft, missionConfig, envSnapshot }: AnalysisPanelProps) {
  const envelopeMutation = useComputeEnvelope();
  const [result, setResult] = useState<EnvelopeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleCompute = () => {
    if (!aircraft) return;
    setError(null);
    const overrides = buildOverridesFromPreset(aircraft, envSnapshot, missionConfig);
    envelopeMutation.mutate(
      {
        twinId: 'default',
        params: {
          grid_resolution: missionConfig?.grid_resolution ?? 20,
          uq_method: missionConfig?.uq_method ?? 'deterministic',
          param_overrides: overrides,
        },
      },
      {
        onSuccess: (data) => setResult(data),
        onError: (err) => setError(err instanceof Error ? err.message : 'Computation failed'),
      },
    );
  };

  const gridSize = result?.speed_altitude_feasibility
    ? `${result.speed_altitude_feasibility.x_values.length}×${result.speed_altitude_feasibility.y_values.length}`
    : undefined;

  const feasiblePct = result?.speed_altitude_feasibility
    ? (() => {
        const mask = result.speed_altitude_feasibility!.feasible_mask ?? result.speed_altitude_feasibility!.z_mean;
        const flat = mask.flat();
        const count = flat.filter((v) => (typeof v === 'boolean' ? v : v > 0.5)).length;
        return flat.length > 0 ? (count / flat.length) * 100 : 0;
      })()
    : undefined;

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 p-4 border-b border-white/[0.06]">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <BarChart3 size={14} className="text-white/50" />
              <span className="text-sm font-semibold text-white/90">Envelope Analysis</span>
            </div>
            <p className="text-[10px] text-white/30 mt-0.5 ml-[22px]">
              Full physics chain evaluated across a speed–altitude grid
            </p>
          </div>
          <div className="flex items-center gap-3">
            {result?.computation_time_s != null && (
              <div className="flex items-center gap-1 text-[10px] text-white/25 font-mono">
                <Clock size={10} />
                {result.computation_time_s.toFixed(1)}s
              </div>
            )}
            <button
              onClick={handleCompute}
              disabled={!aircraft || envelopeMutation.isPending}
              className={clsx(
                'px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all border outline-none',
                'focus-visible:ring-2 focus-visible:ring-white/20',
                aircraft
                  ? 'bg-white/[0.08] text-white/80 border-white/15 hover:bg-white/[0.12] hover:border-white/25'
                  : 'bg-white/[0.03] text-white/20 border-white/[0.05] cursor-not-allowed',
              )}
            >
              {envelopeMutation.isPending ? 'Computing...' : 'Compute Envelope'}
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
        {error && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20">
            <AlertCircle size={14} className="text-red-400 flex-shrink-0" />
            <span className="text-xs text-red-400">{error}</span>
          </div>
        )}

        {!result && !envelopeMutation.isPending && !error && (
          <div className="flex flex-col items-center justify-center py-16 text-center gap-4">
            <Activity size={32} className="text-white/[0.07]" />
            <div>
              <p className="text-sm text-white/30 mb-1">
                {aircraft
                  ? `Analyze the operating envelope for ${aircraft.short_name}`
                  : 'Select an aircraft first'}
              </p>
              <p className="text-[10px] text-white/20 max-w-xs mx-auto">
                Evaluates 17 physics models (aerodynamics, propulsion, optics, AI) across every speed–altitude
                combination to find the feasible operating region.
              </p>
            </div>
          </div>
        )}

        {result && (
          <>
            {/* Primary: Heatmap with ident confidence overlay */}
            <GlassPanel padding="p-4">
              <EnvelopeChart
                surface={result.speed_altitude_feasibility}
                identSurface={result.identification_confidence}
              />
            </GlassPanel>

            {/* Identification confidence line chart */}
            <GlassPanel padding="p-4">
              <IdentConfidence surface={result.identification_confidence} />
            </GlassPanel>

            {/* Side-by-side: Battery + Fuel */}
            <div className="grid grid-cols-2 gap-4">
              <GlassPanel padding="p-4">
                <BatteryReserve output={result.battery_reserve} />
              </GlassPanel>
              <GlassPanel padding="p-4">
                <FuelEndurance output={result.fuel_endurance} flowRate={result.fuel_flow_rate} />
              </GlassPanel>
            </div>

            {/* Side-by-side: Sensitivity + Mission probability */}
            <div className="grid grid-cols-2 gap-4">
              <GlassPanel padding="p-4">
                <SensitivityBars entries={result.sensitivity ?? []} />
              </GlassPanel>
              <GlassPanel padding="p-4">
                <MissionProb
                  probability={result.mission_completion_probability}
                  warnings={result.warnings}
                  computeTimeS={result.computation_time_s}
                  feasiblePct={feasiblePct}
                  gridSize={gridSize}
                />
              </GlassPanel>
            </div>

            {/* Safe inspection speed callout */}
            {result.safe_inspection_speed && (
              <GlassPanel padding="p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-white/40">
                      Recommended Inspection Speed
                    </span>
                    <p className="text-[9px] text-white/25 mt-0.5">
                      Maximum speed that keeps motion blur within safe limits
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="text-xl font-bold font-mono text-emerald-400">
                      {result.safe_inspection_speed.mean.toFixed(1)}
                    </span>
                    <span className="text-[11px] text-white/40 font-mono ml-1.5">
                      {result.safe_inspection_speed.units || 'm/s'}
                    </span>
                  </div>
                </div>
              </GlassPanel>
            )}
          </>
        )}
      </div>
    </div>
  );
}
