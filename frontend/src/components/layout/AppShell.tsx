import React, { useState, useCallback } from 'react';
import { Plane, Map, Cloud, GitBranch } from 'lucide-react';
import { DroneDiagram } from './DroneDiagram';
import { GlassPanel } from './GlassPanel';
import { MetadataForm } from '../forms/MetadataForm';
import { EnvelopeChart } from '../visualization/EnvelopeChart';
import { FuelEndurance } from '../visualization/FuelEndurance';
import { BatteryReserve } from '../visualization/BatteryReserve';
import { MissionProb } from '../visualization/MissionProb';
import { IdentConfidence } from '../visualization/IdentConfidence';
import { SensitivityBars } from '../visualization/SensitivityBars';
import { EnvironmentIntel } from '../environment/EnvironmentIntel';
import type { EnvironmentSnapshot } from '../environment/EnvironmentIntel';
import { ModelPipeline } from '../pipeline/ModelPipeline';
import { clsx } from 'clsx';
import type { SubsystemType } from '../../types/twin';
import type { EnvelopeResponse } from '../../types/envelope';

type ViewMode = 'envelope' | 'environment' | 'pipeline';

interface AppShellProps {
  schema: Record<string, any> | undefined;
  schemaLoading: boolean;
  envelope?: EnvelopeResponse | null;
  computing?: boolean;
  onComputeEnvelope?: (fullParams: Record<string, Record<string, any>>) => void;
}

const SIDE_SUBSYSTEMS: SubsystemType[] = ['airframe', 'mission_profile'];

const VIEW_TABS: { key: ViewMode; label: string; Icon: typeof Plane }[] = [
  { key: 'envelope', label: 'Envelope', Icon: Plane },
  { key: 'environment', label: 'Environment', Icon: Cloud },
  { key: 'pipeline', label: 'Pipeline', Icon: GitBranch },
];

export function AppShell({ schema, schemaLoading, envelope, computing, onComputeEnvelope }: AppShellProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('envelope');
  const [selectedSubsystem, setSelectedSubsystem] = useState<SubsystemType>('airframe');
  const [paramOverrides, setParamOverrides] = useState<Record<string, Record<string, any>>>({});

  const handleValueChange = useCallback(
    (subsystem: SubsystemType, paramName: string, value: any) => {
      setParamOverrides((prev) => ({
        ...prev,
        [subsystem]: {
          ...(prev[subsystem] ?? {}),
          [paramName]: value,
        },
      }));
    },
    [],
  );

  const subsystemSchema = schema?.subsystems?.[selectedSubsystem];
  const currentOverrides = paramOverrides[selectedSubsystem] ?? {};

  const buildFullParams = useCallback((): Record<string, Record<string, any>> => {
    const subs = schema?.subsystems;
    if (!subs) return paramOverrides;
    const full: Record<string, Record<string, any>> = {};
    const subNames = Object.keys(subs).sort();
    for (const subName of subNames) {
      const subSchema = (subs as Record<string, any>)[subName];
      const params = subSchema?.parameters;
      if (!params) continue;
      full[subName] = {};
      const paramNames = Object.keys(params).sort();
      for (const paramName of paramNames) {
        const paramDef = params[paramName] as { value?: any };
        const override = paramOverrides[subName]?.[paramName];
        const raw = override !== undefined ? override : paramDef?.value;
        full[subName][paramName] = raw;
      }
    }
    return full;
  }, [schema, paramOverrides]);

  const handleEnvironmentData = useCallback((snapshot: EnvironmentSnapshot) => {
    setParamOverrides((prev) => ({
      ...prev,
      mission_profile: {
        ...(prev['mission_profile'] ?? {}),
        temperature_c: snapshot.temperature_c,
        pressure_hpa: snapshot.pressure_hpa,
        wind_speed_ms: snapshot.wind_speed_ms,
        wind_direction_deg: snapshot.wind_direction_deg,
        density_altitude_ft: snapshot.density_altitude_ft,
        ambient_light_lux: snapshot.ambient_light_lux,
      },
    }));
  }, []);

  const labelFor = (sub: SubsystemType) =>
    schema?.subsystems?.[sub]?.label ?? sub.replace(/_/g, ' ');

  return (
    <div className="flex h-screen bg-surface-dark/50">
      {/* Left: Side panel - Nav + Envelope Output */}
      <aside className="w-80 flex-shrink-0 p-3 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto min-h-0 space-y-3">
          <GlassPanel padding="p-4">
            <div className="flex items-center gap-2.5 mb-4 px-1">
              <div className="w-9 h-9 rounded-xl bg-gorzen-500/15 flex items-center justify-center shadow-card border border-gorzen-500/20">
                <span className="text-gorzen-400 font-bold text-sm">G</span>
              </div>
              <div>
                <div className="text-sm font-semibold text-white/95 tracking-tight">Gorzen</div>
                <div className="text-[10px] text-white/45 font-medium">Digital Twin</div>
              </div>
            </div>

            {/* View Mode Tabs */}
            <div className="flex gap-1 p-1 rounded-xl bg-white/[0.03] mb-4">
              {VIEW_TABS.map(({ key, label, Icon }) => (
                <button
                  key={key}
                  onClick={() => setViewMode(key)}
                  className={clsx(
                    'flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-[11px] font-medium transition-all duration-200 outline-none',
                    'focus-visible:ring-2 focus-visible:ring-gorzen-500/30',
                    viewMode === key
                      ? 'bg-gorzen-500/15 text-gorzen-400 shadow-card border border-gorzen-500/20'
                      : 'text-white/45 hover:text-white/70 hover:bg-white/[0.04] border border-transparent',
                  )}
                >
                  <Icon size={13} />
                  {label}
                </button>
              ))}
            </div>

            {viewMode === 'envelope' && (
              <>
                <h2 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3 px-1">
                  General
                </h2>
                <nav className="space-y-1">
                  {SIDE_SUBSYSTEMS.map((key) => {
                    const isActive = selectedSubsystem === key;
                    const Icon = key === 'airframe' ? Plane : Map;
                    return (
                      <button
                        key={key}
                        onClick={() => setSelectedSubsystem(key)}
                        className={clsx(
                          'w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all duration-200 outline-none',
                          'focus-visible:ring-2 focus-visible:ring-gorzen-500/30',
                          isActive
                            ? 'bg-gorzen-500/15 text-gorzen-400 border border-gorzen-500/25 shadow-card'
                            : 'text-white/60 hover:text-white/90 hover:bg-white/[0.06] hover:border-white/10 border border-transparent',
                        )}
                      >
                        <Icon size={16} className={isActive ? 'text-gorzen-400' : 'text-white/40'} />
                        <span className="font-medium flex-1 text-left">{labelFor(key)}</span>
                      </button>
                    );
                  })}
                </nav>
                <div className="mt-4 pt-4 border-t border-white/5">
                  <button
                    type="button"
                    onClick={() => onComputeEnvelope?.(buildFullParams())}
                    disabled={computing || !schema}
                    className="glass-button w-full text-center text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {computing ? 'Computing...' : 'Compute Envelope'}
                  </button>
                  {envelope && (
                    <div className="mt-2 text-[10px] text-white/35 text-center font-mono">
                      {envelope.computation_time_s.toFixed(1)}s
                    </div>
                  )}
                </div>
              </>
            )}
          </GlassPanel>

          {/* Envelope output visualizations (only in envelope view) */}
          {viewMode === 'envelope' && (
            <>
              <GlassPanel padding="p-4">
                <MissionProb
                  probability={envelope?.mission_completion_probability}
                  warnings={envelope?.warnings}
                />
              </GlassPanel>
              <GlassPanel padding="p-4">
                <EnvelopeChart surface={envelope?.speed_altitude_feasibility} />
              </GlassPanel>
              <GlassPanel padding="p-4">
                <FuelEndurance output={envelope?.fuel_endurance} flowRate={envelope?.fuel_flow_rate} />
              </GlassPanel>
              <GlassPanel padding="p-4">
                <BatteryReserve output={envelope?.battery_reserve} />
              </GlassPanel>
              <GlassPanel padding="p-4">
                <IdentConfidence surface={envelope?.identification_confidence} />
              </GlassPanel>
              <GlassPanel padding="p-4">
                <SensitivityBars entries={envelope?.sensitivity ?? []} />
              </GlassPanel>
            </>
          )}
        </div>
      </aside>

      {/* Center: View-dependent content */}
      <main className="flex-1 p-4 min-w-0 flex flex-col overflow-hidden">
        {viewMode === 'envelope' && (
          <GlassPanel className="flex-1 min-h-0 overflow-hidden" padding="p-0">
            <div className="w-full h-full min-h-[420px]">
              <DroneDiagram
                selected={selectedSubsystem}
                onSelect={setSelectedSubsystem}
                schema={schema}
              />
            </div>
          </GlassPanel>
        )}
        {viewMode === 'environment' && (
          <GlassPanel className="flex-1 min-h-0 overflow-hidden" padding="p-0">
            <EnvironmentIntel onEnvironmentData={handleEnvironmentData} />
          </GlassPanel>
        )}
        {viewMode === 'pipeline' && (
          <GlassPanel className="flex-1 min-h-0 overflow-hidden" padding="p-0">
            <ModelPipeline />
          </GlassPanel>
        )}
      </main>

      {/* Right: Parameter form (only in envelope view) / Info panel for other views */}
      <aside className="w-[380px] flex-shrink-0 flex flex-col p-3 overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          {viewMode === 'envelope' && (
            <GlassPanel padding="p-6">
              {schemaLoading ? (
                <div className="flex items-center justify-center h-32">
                  <div className="text-white/35 text-sm">Loading...</div>
                </div>
              ) : (
                <MetadataForm
                  subsystem={selectedSubsystem}
                  schema={subsystemSchema}
                  values={currentOverrides}
                  onValueChange={handleValueChange}
                />
              )}
            </GlassPanel>
          )}
          {viewMode === 'environment' && (
            <GlassPanel padding="p-5">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-4">
                About Environment Intelligence
              </h3>
              <div className="space-y-3 text-xs text-white/55 leading-relaxed">
                <p>
                  Real-time atmospheric data from <span className="text-white/80 font-medium">Open-Meteo</span> weather API with multi-altitude wind profiles at 10m, 80m, 120m, and 180m.
                </p>
                <p>
                  Solar position computed analytically from lat/lon/time using <span className="text-white/80 font-medium">Meeus algorithms</span>. Clear-sky irradiance via Ineichen-Perez model.
                </p>
                <div className="pt-2 border-t border-white/[0.06]">
                  <h4 className="text-[10px] font-semibold uppercase tracking-wider text-white/35 mb-2">Auto-Filled Parameters</h4>
                  <div className="space-y-1.5">
                    {[
                      { param: 'temperature_c', label: 'Temperature', val: paramOverrides['mission_profile']?.temperature_c },
                      { param: 'pressure_hpa', label: 'Pressure', val: paramOverrides['mission_profile']?.pressure_hpa },
                      { param: 'wind_speed_ms', label: 'Wind Speed', val: paramOverrides['mission_profile']?.wind_speed_ms },
                      { param: 'wind_direction_deg', label: 'Wind Direction', val: paramOverrides['mission_profile']?.wind_direction_deg },
                      { param: 'density_altitude_ft', label: 'Density Altitude', val: paramOverrides['mission_profile']?.density_altitude_ft },
                      { param: 'ambient_light_lux', label: 'Ambient Light', val: paramOverrides['mission_profile']?.ambient_light_lux },
                    ].map(({ label, val }) => (
                      <div key={label} className="flex items-center justify-between">
                        <span className="text-white/50">{label}</span>
                        <span className="font-mono text-gorzen-400 text-[11px]">
                          {val !== undefined ? (typeof val === 'number' ? val.toFixed(1) : val) : '--'}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-2 text-[10px] text-gorzen-400/60">
                    These values auto-fill the Envelope mission profile from live data.
                  </div>
                </div>
                <div className="pt-2 border-t border-white/[0.06]">
                  <h4 className="text-[10px] font-semibold uppercase tracking-wider text-white/35 mb-2">Data Sources</h4>
                  <div className="space-y-1.5">
                    <div className="flex items-center gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-blue-400" />
                      <span>Open-Meteo (weather, wind profiles)</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                      <span>Analytical solar model (Meeus 1998)</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      <span>ISA + humidity density correction</span>
                    </div>
                  </div>
                </div>
                <div className="pt-2 border-t border-white/[0.06]">
                  <h4 className="text-[10px] font-semibold uppercase tracking-wider text-white/35 mb-2">Flight Categories</h4>
                  <div className="space-y-1">
                    {[
                      { cat: 'VFR', desc: 'Vis > 5sm, Ceiling > 3000ft', color: '#10b981' },
                      { cat: 'MVFR', desc: 'Vis 3-5sm, Ceiling 1000-3000ft', color: '#3b82f6' },
                      { cat: 'IFR', desc: 'Vis 1-3sm, Ceiling 500-1000ft', color: '#f59e0b' },
                      { cat: 'LIFR', desc: 'Vis < 1sm, Ceiling < 500ft', color: '#ef4444' },
                    ].map(({ cat, desc, color }) => (
                      <div key={cat} className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                        <span className="font-mono font-medium text-white/70 w-10">{cat}</span>
                        <span className="text-white/40">{desc}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </GlassPanel>
          )}
          {viewMode === 'pipeline' && (
            <GlassPanel padding="p-5">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-4">
                Model Pipeline Inspector
              </h3>
              <div className="space-y-3 text-xs text-white/55 leading-relaxed">
                <p>
                  Evaluates all <span className="text-white/80 font-medium">17 physics models</span> at a single operating point (speed + altitude) and displays every intermediate value.
                </p>
                <p>
                  The pipeline runs top-to-bottom: Environment through Identification. Each model's outputs feed as inputs to downstream models.
                </p>
                <div className="pt-2 border-t border-white/[0.06]">
                  <h4 className="text-[10px] font-semibold uppercase tracking-wider text-white/35 mb-2">Pipeline Phases</h4>
                  <div className="space-y-1.5">
                    {[
                      { color: '#3b82f6', label: 'Environment', desc: 'ISA density, wind, temperature' },
                      { color: '#06b6d4', label: 'Aerodynamics', desc: 'Drag, lift, flight mode' },
                      { color: '#8b5cf6', label: 'Propulsion & Energy', desc: 'Engine, fuel, rotor, battery' },
                      { color: '#10b981', label: 'Avionics & Compute', desc: 'Nav, inference, comms' },
                      { color: '#f59e0b', label: 'Perception & ID', desc: 'GSD, blur, GIQE, confidence' },
                    ].map(({ color, label, desc }) => (
                      <div key={label} className="flex items-start gap-2">
                        <div className="w-2 h-2 rounded-full mt-1 flex-shrink-0" style={{ backgroundColor: color }} />
                        <div>
                          <span className="text-white/70 font-medium">{label}</span>
                          <span className="text-white/35 ml-1">{desc}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="pt-2 border-t border-white/[0.06]">
                  <h4 className="text-[10px] font-semibold uppercase tracking-wider text-white/35 mb-2">Key Formulas</h4>
                  <div className="space-y-1.5 font-mono text-[10px] text-white/40">
                    <div>GIQE 5: NIIRS = 9.57 - 3.32*ln(GSD) + 3.32*ln(RER)</div>
                    <div>OCV(s) = 3.0 + 2.04s - 5.33s^2 + 12.7s^3</div>
                    <div>T = Ct * rho * n^2 * D^4</div>
                    <div>GSD = (sw * h) / (fl * px)</div>
                  </div>
                </div>
              </div>
            </GlassPanel>
          )}
        </div>
      </aside>
    </div>
  );
}
