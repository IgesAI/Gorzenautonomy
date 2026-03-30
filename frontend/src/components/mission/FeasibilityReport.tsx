import React, { useMemo } from 'react';
import {
  CheckCircle2, AlertTriangle, XCircle, Globe, Eye, Clock,
  Weight, Wind, Thermometer, Camera, Cpu, Home, Zap, ShieldAlert,
} from 'lucide-react';
import { clsx } from 'clsx';
import { computeFeasibility } from '../../data/missions';
import type { AircraftPreset } from '../../data/aircraft';
import type { MissionConfig, FeasibilityAxis, FeasibilityViolation } from '../../data/missions';

interface FeasibilityReportProps {
  aircraft: AircraftPreset;
  config: MissionConfig;
  env?: { wind_ms?: number; temperature_c?: number };
  onPlanMission: () => void;
}

const AXIS_ICONS: Record<string, React.ElementType> = {
  'Optical Resolution': Camera,
  'Image Intelligence (NIIRS)': Eye,
  'Endurance': Clock,
  'Payload Capacity': Weight,
  'Wind Tolerance': Wind,
  'Temperature': Thermometer,
  'Motion Blur': Zap,
};

function ScoreRing({ score, passThreshold = 0.85, warnThreshold = 0.65 }: { score: number; passThreshold?: number; warnThreshold?: number }) {
  const pct = score * 100;
  const color =
    score >= passThreshold ? '#10b981' : score >= warnThreshold ? '#f59e0b' : '#ef4444';
  const r = 22;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;

  return (
    <svg width="56" height="56" viewBox="0 0 56 56">
      <circle
        cx="28" cy="28" r={r}
        fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="3.5"
      />
      <circle
        cx="28" cy="28" r={r}
        fill="none"
        stroke={color}
        strokeWidth="3.5"
        strokeDasharray={`${dash} ${circ - dash}`}
        strokeDashoffset={circ * 0.25}
        strokeLinecap="round"
        style={{ filter: `drop-shadow(0 0 4px ${color}60)` }}
      />
      <text
        x="28" y="32"
        textAnchor="middle"
        fontSize="11"
        fontWeight="700"
        fontFamily="monospace"
        fill={color}
      >
        {pct.toFixed(0)}
      </text>
    </svg>
  );
}

function AxisRow({ axis }: { axis: FeasibilityAxis }) {
  const Icon = AXIS_ICONS[axis.label] ?? CheckCircle2;
  const StatusIcon = axis.pass
    ? CheckCircle2
    : axis.marginal
    ? AlertTriangle
    : XCircle;
  const statusColor = axis.pass
    ? '#10b981'
    : axis.marginal
    ? '#f59e0b'
    : '#ef4444';

  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-white/[0.04] last:border-0">
      <div className="w-7 h-7 rounded-lg bg-white/[0.05] flex items-center justify-center flex-shrink-0">
        <Icon size={13} className="text-white/40" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-white/75 font-medium">{axis.label}</span>
          <StatusIcon size={13} style={{ color: statusColor }} className="flex-shrink-0" />
        </div>
        <div className="text-[10px] text-white/40 mt-0.5">{axis.detail}</div>
        {/* Progress bar */}
        <div className="mt-1.5 h-1 rounded-full bg-white/[0.06] overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${axis.score * 100}%`,
              backgroundColor: statusColor,
              boxShadow: `0 0 6px ${statusColor}40`,
            }}
          />
        </div>
      </div>
      <div className="text-right flex-shrink-0 w-24">
        <div className="text-[11px] font-mono text-white/70">{axis.value_str}</div>
        <div className="text-[9px] text-white/30 font-mono">{axis.requirement_str}</div>
      </div>
    </div>
  );
}

function InferencePipelineCard({ config }: { config: MissionConfig }) {
  const path = config.inference_path;
  const isOnboard = path === 'onboard' || path === 'both';
  const isRTN = path === 'rtn' || path === 'both';

  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-white/35 mb-3 flex items-center gap-1.5">
        <Cpu size={10} className="text-gorzen-400" />
        Inference Pipeline
      </h4>
      <div className="space-y-2">
        <div
          className={clsx(
            'flex items-center gap-3 p-2.5 rounded-lg border transition-colors',
            isOnboard
              ? 'bg-gorzen-500/10 border-gorzen-500/25'
              : 'bg-white/[0.02] border-white/[0.05] opacity-40',
          )}
        >
          <Cpu size={13} className={isOnboard ? 'text-gorzen-400' : 'text-white/30'} />
          <div className="flex-1">
            <div className="text-xs text-white/80 font-medium">Onboard AI</div>
            <div className="text-[10px] text-white/40">
              Real-time detection during flight. Requires AI compute payload.
            </div>
          </div>
          {isOnboard && <CheckCircle2 size={12} className="text-gorzen-400 flex-shrink-0" />}
        </div>

        <div className="flex items-center gap-2 px-3">
          <div className="h-px flex-1 bg-white/[0.06]" />
          <span className="text-[9px] text-white/25">or</span>
          <div className="h-px flex-1 bg-white/[0.06]" />
        </div>

        <div
          className={clsx(
            'flex items-start gap-3 p-2.5 rounded-lg border transition-colors',
            isRTN
              ? 'bg-blue-500/8 border-blue-500/20'
              : 'bg-white/[0.02] border-white/[0.05] opacity-40',
          )}
        >
          <Home size={13} className={isRTN ? 'text-blue-400' : 'text-white/30'} />
          <div className="flex-1">
            <div className="text-xs text-white/80 font-medium">Home Station VLM</div>
            <div className="text-[10px] text-white/40">
              Return footage, run VLM locally. Enables larger models, batch processing.
            </div>
            {isRTN && config.post_processing_hrs > 0 && (
              <div className="text-[10px] text-blue-400/70 mt-1 font-mono">
                Est. processing: {config.post_processing_hrs}h
              </div>
            )}
          </div>
          {isRTN && <CheckCircle2 size={12} className="text-blue-400 flex-shrink-0 mt-0.5" />}
        </div>
      </div>
    </div>
  );
}

function OpticalSimCard({
  gsd,
  niirs,
  detectable_mm,
  altitude_m,
  camera_name,
  target_feature_mm,
  min_gsd,
  min_niirs,
}: {
  gsd: number;
  niirs: number;
  detectable_mm: number;
  altitude_m: number;
  camera_name: string;
  target_feature_mm: number;
  min_gsd: number;
  min_niirs: number;
}) {
  const canResolveTarget = detectable_mm <= target_feature_mm;

  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-white/35 mb-3 flex items-center gap-1.5">
        <Camera size={10} className="text-emerald-400" />
        Optical Simulation
      </h4>

      <div className="grid grid-cols-3 gap-2 mb-4">
        {[
          { label: 'GSD', val: `${gsd.toFixed(2)} cm/px`, color: gsd <= min_gsd ? '#10b981' : '#f59e0b' },
          { label: 'NIIRS', val: niirs.toFixed(1), color: niirs >= min_niirs ? '#10b981' : '#f59e0b' },
          { label: 'Min Feature', val: `${detectable_mm.toFixed(0)} mm`, color: detectable_mm <= target_feature_mm ? '#10b981' : '#f59e0b' },
        ].map(({ label, val, color }) => (
          <div key={label} className="bg-white/[0.04] rounded-lg p-2 text-center border border-white/[0.05]">
            <div className="text-[9px] text-white/30">{label}</div>
            <div className="text-sm font-mono font-bold mt-0.5" style={{ color }}>{val}</div>
          </div>
        ))}
      </div>

      {/* Visual scale diagram */}
      <div className="bg-black/20 rounded-lg p-3 border border-white/[0.05]">
        <div className="text-[9px] text-white/30 mb-2">
          Pixel footprint at {altitude_m} m AGL — {camera_name}
        </div>
        <svg viewBox="0 0 200 60" className="w-full" style={{ height: 60 }}>
          <line x1="0" y1="50" x2="200" y2="50" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
          <rect x="20" y="38" width={Math.min(180, gsd * 60)} height="8" rx="1"
            fill="rgba(99,102,241,0.4)" stroke="rgba(99,102,241,0.6)" strokeWidth="0.5" />
          <text x="20" y="35" fontSize="7" fill="rgba(255,255,255,0.4)">
            1 pixel = {(gsd * 10).toFixed(1)} mm
          </text>
          <line x1="120" y1="38" x2="120" y2="46" stroke="#ef4444" strokeWidth="1" />
          <text x="122" y="44" fontSize="7" fill="#ef444480">{target_feature_mm}mm target</text>
          <line x1="100" y1="5" x2="100" y2="37" stroke="rgba(255,255,255,0.08)"
            strokeWidth="0.5" strokeDasharray="3,2" />
          <text x="102" y="12" fontSize="7" fill="rgba(255,255,255,0.3)">{altitude_m}m AGL</text>
          <polygon
            points="100,5 60,38 140,38"
            fill="rgba(255,255,255,0.03)"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth="0.5"
          />
        </svg>

        <div className="mt-2 flex items-center gap-1.5">
          {canResolveTarget ? (
            <CheckCircle2 size={10} className="text-emerald-400" />
          ) : (
            <XCircle size={10} className="text-red-400" />
          )}
          <span className={clsx(
            'text-[10px] font-medium',
            canResolveTarget ? 'text-emerald-400' : 'text-red-400',
          )}>
            {canResolveTarget
              ? `Can resolve ${target_feature_mm}mm features at this altitude`
              : `Cannot resolve ${target_feature_mm}mm features — min detectable: ${detectable_mm.toFixed(0)}mm`}
          </span>
        </div>
      </div>
    </div>
  );
}

export function FeasibilityReport({
  aircraft,
  config,
  env,
  onPlanMission,
}: FeasibilityReportProps) {
  const result = useMemo(
    () => computeFeasibility(aircraft, config, env),
    [aircraft, config, env],
  );

  const overallPct = (result.overall * 100).toFixed(1);
  const overallColor =
    result.viable ? '#10b981' : result.marginal ? '#f59e0b' : '#ef4444';
  const overallLabel = result.viable ? 'GO' : result.marginal ? 'MARGINAL' : 'NO-GO';

  return (
    <div className="h-full flex flex-col">
      {/* Header verdict */}
      <div
        className="flex-shrink-0 p-5 border-b border-white/[0.06]"
        style={{ background: `linear-gradient(135deg, ${overallColor}08 0%, transparent 60%)` }}
      >
        <div className="flex items-center gap-4">
          <ScoreRing score={result.overall} passThreshold={config.pass_threshold} warnThreshold={config.warn_threshold} />
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2 flex-wrap">
              <span
                className="text-2xl font-black font-mono tracking-tight"
                style={{ color: overallColor }}
              >
                {overallPct}%
              </span>
              <span
                className="text-sm font-bold px-2.5 py-0.5 rounded-lg uppercase tracking-wider"
                style={{
                  backgroundColor: `${overallColor}18`,
                  color: overallColor,
                  border: `1px solid ${overallColor}30`,
                }}
              >
                {overallLabel}
              </span>
            </div>
            <div className="text-xs text-white/50 mt-0.5">
              {aircraft.short_name} — {config.nominal_altitude_m}m AGL @ {config.nominal_speed_ms} m/s
            </div>
          </div>

          {result.viable && (
            <button
              onClick={onPlanMission}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200
                bg-gorzen-500/15 text-gorzen-400 border border-gorzen-500/30
                hover:bg-gorzen-500/25 hover:border-gorzen-500/50 outline-none
                focus-visible:ring-2 focus-visible:ring-gorzen-500/40"
            >
              <Globe size={14} />
              Plan Mission
            </button>
          )}
        </div>

        {!result.viable && !result.marginal && (
          <div className="mt-3 p-3 rounded-lg bg-red-500/8 border border-red-500/15 text-[11px] text-red-400/80">
            This aircraft cannot meet the mission requirements. Select a different aircraft or adjust the parameters on the left.
          </div>
        )}
        {result.marginal && (
          <div className="mt-3 p-3 rounded-lg bg-amber-500/8 border border-amber-500/15 text-[11px] text-amber-400/80">
            Marginal feasibility — mission may succeed under ideal conditions. Review limiting axes below.
          </div>
        )}
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5 min-h-0">
        {/* Axes */}
        <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-2">
          {result.axes.map((ax) => (
            <AxisRow key={ax.label} axis={ax} />
          ))}
        </div>

        {/* Optical simulation */}
        <OpticalSimCard
          gsd={result.gsd_cm_per_px}
          niirs={result.niirs}
          detectable_mm={result.detectable_crack_mm}
          altitude_m={config.nominal_altitude_m}
          camera_name={aircraft.default_camera.name}
          target_feature_mm={config.target_feature_mm}
          min_gsd={config.min_gsd_cm_per_px}
          min_niirs={config.min_niirs}
        />

        {/* Violations */}
        {result.violations.length > 0 && (
          <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
            <h4 className="text-[10px] font-semibold uppercase tracking-wider text-amber-400/60 mb-3 flex items-center gap-1.5">
              <ShieldAlert size={10} className="text-amber-400" />
              Validation Violations ({result.violations.length})
            </h4>
            <div className="space-y-2">
              {result.violations.map((v, i) => (
                <div key={i} className="text-[10px] p-2 rounded-lg bg-black/20 border border-white/[0.05]">
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className={clsx(
                      'px-1.5 py-0.5 rounded text-[8px] font-bold uppercase',
                      v.type === 'missing_data' ? 'bg-red-500/20 text-red-400' :
                      v.type === 'estimated_param' ? 'bg-amber-500/20 text-amber-400' :
                      'bg-orange-500/20 text-orange-400',
                    )}>
                      {v.type.replace('_', ' ')}
                    </span>
                    <span className="text-white/50 font-mono">{v.parameter}</span>
                  </div>
                  <div className="text-white/40">{v.impact}</div>
                  <div className="text-gorzen-400/60 mt-0.5">{v.correction}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Confidence */}
        <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-white/35">
              Data Confidence
            </span>
            <span className={clsx(
              'px-2 py-0.5 rounded-lg text-[10px] font-bold uppercase',
              result.confidence === 'HIGH' && 'bg-emerald-500/15 text-emerald-400',
              result.confidence === 'MEDIUM' && 'bg-blue-500/15 text-blue-400',
              result.confidence === 'LOW' && 'bg-amber-500/15 text-amber-400',
              result.confidence === 'INSUFFICIENT_DATA' && 'bg-red-500/15 text-red-400',
            )}>
              {result.confidence}
            </span>
          </div>
        </div>

        {/* Inference pipeline */}
        <InferencePipelineCard config={config} />
      </div>
    </div>
  );
}
