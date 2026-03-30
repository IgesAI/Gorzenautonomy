import { useState, useCallback } from 'react';
import { Globe, Radio, FileText, Cloud, BarChart3, ChevronLeft, ChevronRight, Crosshair } from 'lucide-react';
import { clsx } from 'clsx';
import { ErrorBoundary } from 'react-error-boundary';

import { GlassPanel } from './GlassPanel';
import { FleetSelector } from '../fleet/FleetSelector';
import { MissionEditor } from '../mission/MissionEditor';
import { FeasibilityReport } from '../mission/FeasibilityReport';
import { MissionPlanner } from '../mission/MissionPlanner';
import { EnvironmentIntel } from '../environment/EnvironmentIntel';
import type { EnvironmentSnapshot } from '../environment/EnvironmentIntel';
import { LiveTelemetry } from '../telemetry/LiveTelemetry';
import { FlightLogAnalyzer } from '../telemetry/FlightLogAnalyzer';
import { AnalysisPanel } from '../analysis/AnalysisPanel';

import { AIRCRAFT_BY_ID } from '../../data/aircraft';
import type { AircraftPreset } from '../../data/aircraft';
import { DEFAULT_MISSION_CONFIG } from '../../data/missions';
import type { MissionConfig } from '../../data/missions';

type SecondaryView = 'environment' | 'analysis' | 'telemetry' | 'logs' | 'mission';

interface AppShellProps {
  selectedAircraftId: string | null;
  onSelectAircraft: (id: string) => void;
  missionConfig: MissionConfig | null;
  onMissionConfigChange: (config: MissionConfig | null) => void;
  geoLocation: { lat: number; lon: number } | null;
  envSnapshot: { wind_ms?: number; temperature_c?: number };
  onEnvUpdate: (wind_ms: number, temperature_c: number) => void;
}

const SECONDARY_TABS = [
  { key: 'environment' as SecondaryView, label: 'Weather', Icon: Cloud },
  { key: 'mission' as SecondaryView, label: 'Flight Plan', Icon: Globe },
  { key: 'analysis' as SecondaryView, label: 'Analysis', Icon: BarChart3 },
  { key: 'telemetry' as SecondaryView, label: 'Live', Icon: Radio },
  { key: 'logs' as SecondaryView, label: 'Logs', Icon: FileText },
];

export function AppShell({
  selectedAircraftId,
  onSelectAircraft,
  missionConfig,
  onMissionConfigChange,
  geoLocation,
  envSnapshot,
  onEnvUpdate,
}: AppShellProps) {
  const [secondaryView, setSecondaryView] = useState<SecondaryView | null>(null);
  const [leftCollapsed, setLeftCollapsed] = useState(false);

  const aircraft = selectedAircraftId ? AIRCRAFT_BY_ID[selectedAircraftId] : null;
  const bothSelected = !!aircraft && !!missionConfig;

  const handleEnvironmentData = useCallback(
    (snap: EnvironmentSnapshot) => {
      onEnvUpdate(snap.wind_speed_ms ?? 0, snap.temperature_c ?? 15);
    },
    [onEnvUpdate],
  );

  const handlePlanMission = useCallback(() => {
    setSecondaryView('mission');
  }, []);

  const handleConfigChange = useCallback(
    (config: MissionConfig) => {
      onMissionConfigChange(config);
    },
    [onMissionConfigChange],
  );

  const handleStartConfiguring = useCallback(() => {
    onMissionConfigChange({ ...DEFAULT_MISSION_CONFIG });
  }, [onMissionConfigChange]);

  const handleTelemetryUpdate = useCallback(
    (data: { wind_speed_ms: number; temperature_c: number }) => {
      onEnvUpdate(data.wind_speed_ms, data.temperature_c);
    },
    [onEnvUpdate],
  );


  return (
    <div className="flex h-screen bg-surface-dark/50 overflow-hidden">

      {/* ── LEFT: Fleet + Mission editor ──────────────────────────────── */}
      <aside
        className={clsx(
          'flex-shrink-0 flex flex-col transition-all duration-300 overflow-hidden',
          leftCollapsed ? 'w-12' : 'w-80',
        )}
      >
        {/* Collapse toggle */}
        <div className="flex items-center justify-between px-3 pt-3 pb-1 flex-shrink-0 bg-black">
          {!leftCollapsed && (
            <div className="flex flex-col items-start">
              <img
                src="/vertical_autonomy_white_on_black.png"
                alt="Vertical Autonomy"
                className="w-[500px] h-auto max-h-20 object-cover object-center"
              />
              <span className="text-[7px] uppercase tracking-[0.3em] text-white/20 mt-0.5 ml-0.5">
                Mission Intelligence
              </span>
            </div>
          )}
          <button
            onClick={() => setLeftCollapsed((v) => !v)}
            className={clsx(
              'w-7 h-7 rounded-lg flex items-center justify-center transition-all',
              'text-white/30 hover:text-white/70 hover:bg-white/[0.06]',
              leftCollapsed && 'mx-auto',
            )}
          >
            {leftCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </button>
        </div>

        {!leftCollapsed && (
          <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-5 min-h-0 mt-2">
            {/* Fleet */}
            <FleetSelector
              selectedId={selectedAircraftId}
              onSelect={onSelectAircraft}
            />

            {/* Mission config */}
            {missionConfig ? (
              <MissionEditor
                config={missionConfig}
                onChange={handleConfigChange}
              />
            ) : (
              <div className="text-center py-4">
                <button
                  onClick={handleStartConfiguring}
                  className="px-4 py-2 rounded-xl text-xs font-medium transition-all
                    bg-gorzen-500/15 text-gorzen-400 border border-gorzen-500/30
                    hover:bg-gorzen-500/25 hover:border-gorzen-500/50 outline-none
                    focus-visible:ring-2 focus-visible:ring-gorzen-500/40"
                >
                  Define Mission Parameters
                </button>
                <p className="text-[10px] text-white/30 mt-2">
                  Configure GSD, altitude, speed, and more
                </p>
              </div>
            )}
          </div>
        )}
      </aside>

      {/* ── CENTER: Feasibility or secondary view ────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden p-3 gap-3">

        {/* Secondary tool tabs */}
        <div className="flex-shrink-0 flex items-center gap-1 p-1 rounded-xl bg-white/[0.03] border border-white/[0.05] self-start">
          <button
            onClick={() => setSecondaryView(null)}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all duration-150 outline-none whitespace-nowrap',
              'focus-visible:ring-2 focus-visible:ring-gorzen-500/30',
              secondaryView === null
                ? 'bg-gorzen-500/15 text-gorzen-400 border border-gorzen-500/20'
                : 'text-white/40 hover:text-white/70 hover:bg-white/[0.04] border border-transparent',
            )}
          >
            <Crosshair size={12} />
            Feasibility
          </button>
          {SECONDARY_TABS.map(({ key, label, Icon }) => (
            <button
              key={key}
              onClick={() => setSecondaryView(key)}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all duration-150 outline-none whitespace-nowrap',
                'focus-visible:ring-2 focus-visible:ring-gorzen-500/30',
                secondaryView === key
                  ? 'bg-gorzen-500/15 text-gorzen-400 border border-gorzen-500/20'
                  : 'text-white/40 hover:text-white/70 hover:bg-white/[0.04] border border-transparent',
              )}
            >
              <Icon size={12} />
              {label}
            </button>
          ))}
        </div>

        {/* View content */}
        <GlassPanel className="flex-1 min-h-0 overflow-hidden" padding="p-0">
          {secondaryView === null && (
            <div className="h-full relative overflow-hidden bg-black">
              {/* Faint grey wireframe — always visible */}
              <img
                src="/drone-hero.png"
                alt=""
                className="absolute inset-0 w-full h-full object-contain select-none pointer-events-none"
                style={{ opacity: 0.15 }}
                loading="lazy"
                draggable={false}
              />
              {/* Purple sweep animation over the drone */}
              <img
                src="/drone-hero.png"
                alt=""
                className="absolute inset-0 w-full h-full object-contain select-none pointer-events-none drone-sweep-clip"
                style={{ filter: 'brightness(0.9) sepia(1) hue-rotate(240deg) saturate(5)' }}
                loading="lazy"
                draggable={false}
              />

              {bothSelected ? (
                <div className="absolute inset-0 z-10 flex items-stretch">
                  <div
                    className="flex-1 overflow-hidden rounded-2xl m-4 border border-white/[0.08]"
                    style={{
                      background: 'rgba(0, 0, 0, 0.45)',
                      backdropFilter: 'blur(16px) saturate(150%)',
                      WebkitBackdropFilter: 'blur(16px) saturate(150%)',
                    }}
                  >
                    <FeasibilityReport
                      aircraft={aircraft!}
                      config={missionConfig!}
                      env={envSnapshot}
                      onPlanMission={handlePlanMission}
                    />
                  </div>
                </div>
              ) : (
                <EmptyFeasibilityOverlay
                  hasAircraft={!!aircraft}
                  hasConfig={!!missionConfig}
                />
              )}
            </div>
          )}

          {secondaryView === 'environment' && (
            <ErrorBoundary fallback={<div className="h-full flex items-center justify-center text-red-400 text-sm p-6">Environment panel failed to load.</div>}>
              <EnvironmentIntel
                onEnvironmentData={handleEnvironmentData}
                sharedLocation={geoLocation}
              />
            </ErrorBoundary>
          )}

          {secondaryView === 'analysis' && (
            <ErrorBoundary fallback={<div className="h-full flex items-center justify-center text-red-400 text-sm p-6">Analysis panel failed to load.</div>}>
              <AnalysisPanel aircraft={aircraft} missionConfig={missionConfig} envSnapshot={envSnapshot} />
            </ErrorBoundary>
          )}

          {secondaryView === 'telemetry' && (
            <ErrorBoundary fallback={<div className="h-full flex items-center justify-center text-red-400 text-sm p-6">Telemetry panel failed to load.</div>}>
              <LiveTelemetry onTelemetryUpdate={handleTelemetryUpdate} />
            </ErrorBoundary>
          )}

          {secondaryView === 'logs' && (
            <ErrorBoundary fallback={<div className="h-full flex items-center justify-center text-red-400 text-sm p-6">Flight log analyzer failed to load.</div>}>
              <FlightLogAnalyzer />
            </ErrorBoundary>
          )}

          {secondaryView === 'mission' && (
            <ErrorBoundary
              fallback={
                <div className="h-full flex items-center justify-center text-red-400 text-sm p-6">
                  Mission globe failed to load. Check WebGL or reload.
                </div>
              }
            >
              <MissionPlanner
                sharedLocation={geoLocation}
                twinId={selectedAircraftId ?? 'default'}
                missionConfig={missionConfig}
              />
            </ErrorBoundary>
          )}
        </GlassPanel>
      </main>

      {/* ── RIGHT: Context panel ─────────────────────────────────────────── */}
      <aside className="w-72 flex-shrink-0 p-3 overflow-hidden flex flex-col">
        <div className="flex-1 overflow-y-auto min-h-0">
          <RightPanel
            aircraft={aircraft}
            config={missionConfig}
            envSnapshot={envSnapshot}
            secondaryView={secondaryView}
          />
        </div>
      </aside>
    </div>
  );
}

// ─── Empty state ─────────────────────────────────────────────────────────────

function EmptyFeasibilityOverlay({
  hasAircraft,
  hasConfig,
}: {
  hasAircraft: boolean;
  hasConfig: boolean;
}) {
  return (
    <div className="relative z-10 h-full flex flex-col items-center justify-end pb-16 p-8 text-center gap-5">
      <div className="flex items-center gap-3">
        <StepBadge
          n={1}
          label="Select Aircraft"
          done={hasAircraft}
          active={!hasAircraft}
        />
        <div className="w-8 h-px bg-white/[0.08]" />
        <StepBadge
          n={2}
          label="Configure Mission"
          done={hasConfig}
          active={hasAircraft && !hasConfig}
        />
        <div className="w-8 h-px bg-white/[0.08]" />
        <StepBadge
          n={3}
          label="Review Feasibility"
          done={false}
          active={hasAircraft && hasConfig}
        />
      </div>

      <div className="max-w-sm">
        {!hasAircraft && !hasConfig && (
          <p className="text-sm text-white/40 leading-relaxed">
            Select an aircraft from your fleet, then define mission parameters to determine if your target detection requirements are achievable.
          </p>
        )}
        {hasAircraft && !hasConfig && (
          <p className="text-sm text-white/40 leading-relaxed">
            Click "Define Mission Parameters" on the left to set your imaging, altitude, and detection requirements.
          </p>
        )}
      </div>
    </div>
  );
}

function StepBadge({
  n,
  label,
  done,
  active,
}: {
  n: number;
  label: string;
  done: boolean;
  active: boolean;
}) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div
        className={clsx(
          'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border',
          done
            ? 'bg-gorzen-500/20 text-gorzen-400 border-gorzen-500/30'
            : active
            ? 'bg-white/[0.08] text-white/70 border-white/20 animate-pulse'
            : 'bg-white/[0.03] text-white/25 border-white/10',
        )}
      >
        {done ? '✓' : n}
      </div>
      <span
        className={clsx(
          'text-[9px] uppercase tracking-wider font-semibold whitespace-nowrap',
          done ? 'text-gorzen-400/70' : active ? 'text-white/50' : 'text-white/20',
        )}
      >
        {label}
      </span>
    </div>
  );
}

// ─── Right panel content ─────────────────────────────────────────────────────

function RightPanel({
  aircraft,
  config,
  envSnapshot,
  secondaryView,
}: {
  aircraft: AircraftPreset | null;
  config: MissionConfig | null;
  envSnapshot: { wind_ms?: number; temperature_c?: number };
  secondaryView: SecondaryView | null;
}) {
  if (secondaryView === 'environment') {
    return <EnvContextPanel envSnapshot={envSnapshot} />;
  }

  const INFER_LABELS: Record<string, string> = {
    onboard: 'Onboard AI',
    rtn: 'Home Station',
    both: 'Either',
  };

  return (
    <div className="space-y-3">
      {/* Aircraft spec card */}
      {aircraft ? (
        <GlassPanel padding="p-4">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-white/35 mb-3">
            Aircraft
          </div>
          <div className="text-sm font-bold text-white/90 mb-0.5">{aircraft.name}</div>
          <div className="text-[10px] text-white/40 font-mono mb-3">{aircraft.engine.model}</div>
          <div className="space-y-2">
            {[
              ['MTOW', `${aircraft.mtow_kg} kg`],
              ['Payload', `${aircraft.payload_max_kg} kg`],
              ['Endurance', `${aircraft.endurance_min} min`],
              ['Engine', `${aircraft.engine.power_kw} kW / ${aircraft.engine.power_hp} HP`],
              ['Fuel', aircraft.fuel_type === 'heavy_fuel' ? 'JP5/JP8/Jet-A' : 'Gasoline'],
              ['Arch', aircraft.propulsion_arch === 'series_hybrid' ? 'Series Hybrid' : 'Direct ICE'],
              ['Max Speed', `${aircraft.max_speed_ms} m/s`],
              ['Wind Limit', `${aircraft.wind_limit_ms} m/s`],
              ['Camera', aircraft.default_camera.name],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between">
                <span className="text-[10px] text-white/35">{k}</span>
                <span className="text-[10px] font-mono text-white/65">{v}</span>
              </div>
            ))}
          </div>
          <a
            href={aircraft.datasheet_path}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 flex items-center gap-1.5 text-[10px] text-gorzen-400/60 hover:text-gorzen-400 transition-colors"
          >
            <FileText size={10} />
            View Datasheet
          </a>
        </GlassPanel>
      ) : (
        <GlassPanel padding="p-4">
          <div className="text-center py-4">
            <div className="text-[10px] text-white/25">No aircraft selected</div>
            <div className="text-[9px] text-white/15 mt-1">Choose from the fleet panel on the left</div>
          </div>
        </GlassPanel>
      )}

      {/* Mission config card */}
      {config ? (
        <GlassPanel padding="p-4">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-white/35 mb-3">
            Mission Requirements
          </div>
          <div className="space-y-2">
            {[
              ['GSD', `≤ ${config.min_gsd_cm_per_px} cm/px`],
              ['NIIRS', `≥ ${config.min_niirs}`],
              ['Target', `${config.target_feature_mm} mm`],
              ['Altitude', `${config.nominal_altitude_m} m AGL`],
              ['Speed', `${config.nominal_speed_ms} m/s`],
              ['Endurance', `${config.min_endurance_min} min`],
              ['Payload', `${config.required_payload_kg} kg`],
              ['Wind', `≤ ${config.max_wind_ms} m/s`],
              ['Inference', INFER_LABELS[config.inference_path] ?? config.inference_path],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between">
                <span className="text-[10px] text-white/35">{k}</span>
                <span className="text-[10px] font-mono text-white/65">{v}</span>
              </div>
            ))}
          </div>
        </GlassPanel>
      ) : (
        <GlassPanel padding="p-4">
          <div className="text-center py-4">
            <div className="text-[10px] text-white/25">No mission configured</div>
            <div className="text-[9px] text-white/15 mt-1">Define parameters like GSD, altitude, and speed</div>
          </div>
        </GlassPanel>
      )}

      {/* Live env */}
      {(envSnapshot.wind_ms != null || envSnapshot.temperature_c != null) && (
        <GlassPanel padding="p-4">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-white/35 mb-3 flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Live Environment
          </div>
          <div className="space-y-2">
            {envSnapshot.wind_ms != null && (
              <div className="flex justify-between">
                <span className="text-[10px] text-white/35">Wind</span>
                <span className="text-[10px] font-mono text-white/65">{envSnapshot.wind_ms.toFixed(1)} m/s</span>
              </div>
            )}
            {envSnapshot.temperature_c != null && (
              <div className="flex justify-between">
                <span className="text-[10px] text-white/35">Temperature</span>
                <span className="text-[10px] font-mono text-white/65">{envSnapshot.temperature_c.toFixed(1)} °C</span>
              </div>
            )}
          </div>
        </GlassPanel>
      )}
    </div>
  );
}

function EnvContextPanel({
  envSnapshot,
}: {
  envSnapshot: { wind_ms?: number; temperature_c?: number };
}) {
  return (
    <GlassPanel padding="p-5">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-4">
        Environment Intelligence
      </h3>
      <div className="space-y-3 text-xs text-white/55 leading-relaxed">
        <p>
          Real-time atmospheric data from{' '}
          <span className="text-white/80 font-medium">Open-Meteo</span> with
          multi-altitude wind profiles at 10m, 80m, 120m, 180m.
        </p>
        <p>
          Live data feeds directly into the feasibility engine — wind and
          temperature affect the go/no-go score for the selected aircraft.
        </p>
        {(envSnapshot.wind_ms != null || envSnapshot.temperature_c != null) && (
          <div className="pt-2 border-t border-white/[0.06] space-y-1.5">
            {envSnapshot.wind_ms != null && (
              <div className="flex justify-between">
                <span className="text-white/40">Wind</span>
                <span className="font-mono text-gorzen-400 text-[11px]">
                  {envSnapshot.wind_ms.toFixed(1)} m/s
                </span>
              </div>
            )}
            {envSnapshot.temperature_c != null && (
              <div className="flex justify-between">
                <span className="text-white/40">Temperature</span>
                <span className="font-mono text-gorzen-400 text-[11px]">
                  {envSnapshot.temperature_c.toFixed(1)} °C
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </GlassPanel>
  );
}
