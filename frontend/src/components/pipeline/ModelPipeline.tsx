import React, { useState, useEffect } from 'react';
import { GlassPanel } from '../layout/GlassPanel';
import { chartStyles } from '../../theme/chartStyles';
import { colors, getConfidenceColor } from '../../theme/tokens';
import { api } from '../../api/client';

interface StageData {
  [key: string]: number | string;
}

interface ModelChainResult {
  speed_ms: number;
  altitude_m: number;
  stages: Record<string, StageData>;
  niirs_interpretation: {
    level: number;
    category: string;
    description: string;
    tasks: string[];
  };
}

const STAGE_META: { key: string; label: string; icon: string; color: string }[] = [
  { key: 'environment', label: '1. Environment', icon: 'cloud', color: '#3b82f6' },
  { key: 'airframe', label: '2. Airframe', icon: 'plane', color: '#06b6d4' },
  { key: 'ice_engine', label: '3. ICE Engine', icon: 'zap', color: '#8b5cf6' },
  { key: 'fuel_system', label: '4. Fuel System', icon: 'fuel', color: '#8b5cf6' },
  { key: 'rotor', label: '5. Rotor', icon: 'fan', color: '#8b5cf6' },
  { key: 'motor', label: '6. Motor', icon: 'bolt', color: '#8b5cf6' },
  { key: 'esc', label: '7. ESC', icon: 'cpu', color: '#8b5cf6' },
  { key: 'battery', label: '8. Battery', icon: 'battery', color: '#8b5cf6' },
  { key: 'generator', label: '9. Generator', icon: 'refresh', color: '#8b5cf6' },
  { key: 'avionics', label: '10. Avionics', icon: 'compass', color: '#10b981' },
  { key: 'compute', label: '11. Compute', icon: 'cpu', color: '#10b981' },
  { key: 'comms', label: '12. Comms', icon: 'radio', color: '#10b981' },
  { key: 'gsd', label: '13. GSD', icon: 'eye', color: '#f59e0b' },
  { key: 'motion_blur', label: '14. Motion Blur', icon: 'blur', color: '#f59e0b' },
  { key: 'rolling_shutter', label: '15. Rolling Shutter', icon: 'camera', color: '#f59e0b' },
  { key: 'image_quality', label: '16. Image Quality', icon: 'image', color: '#f59e0b' },
  { key: 'identification', label: '17. Identification', icon: 'target', color: '#ef4444' },
];

const PHASE_GROUPS = [
  { label: 'Environment', color: '#3b82f6', stages: ['environment'] },
  { label: 'Aerodynamics', color: '#06b6d4', stages: ['airframe'] },
  { label: 'Propulsion & Energy', color: '#8b5cf6', stages: ['ice_engine', 'fuel_system', 'rotor', 'motor', 'esc', 'battery', 'generator'] },
  { label: 'Avionics & Compute', color: '#10b981', stages: ['avionics', 'compute', 'comms'] },
  { label: 'Perception & ID', color: '#f59e0b', stages: ['gsd', 'motion_blur', 'rolling_shutter', 'image_quality', 'identification'] },
];

function formatValue(key: string, val: number | string): string {
  if (typeof val === 'string') return val;
  if (key.includes('feasible') || key.includes('active')) return val > 0.5 ? 'PASS' : 'FAIL';
  if (key.includes('pct')) return val.toFixed(1) + '%';
  if (Math.abs(val) >= 1000) return val.toFixed(0);
  if (Math.abs(val) >= 1) return val.toFixed(1);
  return val.toFixed(3);
}

function StageCard({ stageKey, label, color, data, expanded, onToggle }: {
  stageKey: string; label: string; color: string; data: StageData | undefined;
  expanded: boolean; onToggle: () => void;
}) {
  if (!data) return null;
  const entries = Object.entries(data);

  return (
    <div
      className="rounded-xl border transition-all duration-200 overflow-hidden cursor-pointer"
      style={{
        borderColor: expanded ? color + '40' : 'rgba(255,255,255,0.06)',
        background: expanded ? color + '08' : 'rgba(255,255,255,0.02)',
      }}
      onClick={onToggle}
    >
      <div className="flex items-center gap-2 px-3 py-2">
        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
        <span className="text-xs font-semibold text-white/80 flex-1">{label}</span>
        {entries.some(([k, v]) => k.includes('feasible') && typeof v === 'number' && v < 0.5) && (
          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-red-500/20 text-red-400">FAIL</span>
        )}
        <svg width={12} height={12} viewBox="0 0 12 12" className={`transition-transform ${expanded ? 'rotate-180' : ''}`}>
          <path d="M3 4.5 L6 7.5 L9 4.5" fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth={1.5} />
        </svg>
      </div>
      {expanded && (
        <div className="px-3 pb-2.5 space-y-1 border-t border-white/[0.04]">
          {entries.map(([key, val]) => {
            const isFeasible = key.includes('feasible') || key.includes('active');
            const numVal = typeof val === 'number' ? val : 0;
            return (
              <div key={key} className="flex items-center justify-between py-0.5">
                <span className="text-[10px] text-white/50 font-mono truncate mr-2">
                  {key.replace(/_/g, ' ')}
                </span>
                <span
                  className="text-[11px] font-mono font-medium tabular-nums"
                  style={{
                    color: isFeasible
                      ? (numVal > 0.5 ? colors.status.success : colors.status.danger)
                      : 'rgba(255,255,255,0.85)',
                  }}
                >
                  {formatValue(key, val)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function ModelPipeline() {
  const [result, setResult] = useState<ModelChainResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [speed, setSpeed] = useState(15);
  const [altitude, setAltitude] = useState(50);
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['identification', 'image_quality']));

  const evaluate = async () => {
    setLoading(true);
    try {
      const data = await api.environment.modelChain(speed, altitude);
      setResult(data);
    } catch (e) {
      console.error('Model chain evaluation failed:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { evaluate(); }, []);

  const toggleStage = (key: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const conf = result?.stages?.identification?.identification_confidence;
  const confVal = typeof conf === 'number' ? conf : 0;

  return (
    <div className="h-full overflow-y-auto space-y-3 p-3">
      {/* Controls */}
      <GlassPanel padding="p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className={chartStyles.title}>17-Model Pipeline Inspector</h2>
            <p className="text-[10px] text-white/35 mt-0.5">Single-point deep dive into every physics stage</p>
          </div>
          <button onClick={evaluate} disabled={loading} className="glass-button text-xs py-1.5 px-3 disabled:opacity-50">
            {loading ? 'Evaluating...' : 'Evaluate'}
          </button>
        </div>
        <div className="flex gap-4">
          <div className="flex-1">
            <label className="text-[10px] text-white/40 block mb-1">Speed (m/s)</label>
            <div className="flex items-center gap-2">
              <input type="range" min={0.5} max={35} step={0.5} value={speed}
                aria-label="Speed"
                onChange={e => setSpeed(+e.target.value)} className="glass-slider flex-1" />
              <span className="text-xs font-mono text-white/70 w-10 text-right">{speed}</span>
            </div>
          </div>
          <div className="flex-1">
            <label className="text-[10px] text-white/40 block mb-1">Altitude (m)</label>
            <div className="flex items-center gap-2">
              <input type="range" min={10} max={200} step={5} value={altitude}
                aria-label="Altitude"
                onChange={e => setAltitude(+e.target.value)} className="glass-slider flex-1" />
              <span className="text-xs font-mono text-white/70 w-10 text-right">{altitude}</span>
            </div>
          </div>
        </div>
      </GlassPanel>

      {/* Final Output Summary */}
      {result && (
        <GlassPanel padding="p-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className={chartStyles.title}>Pipeline Output</h3>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-2xl font-bold font-mono" style={{ color: getConfidenceColor(confVal) }}>
                  {(confVal * 100).toFixed(1)}%
                </span>
                <span className="text-xs text-white/40">identification confidence</span>
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs text-white/40">NIIRS</div>
              <div className="text-lg font-bold font-mono text-white/90">
                {result.stages.image_quality?.niirs_equivalent}
              </div>
              <div className="text-[10px] text-white/30">{result.niirs_interpretation.category}</div>
            </div>
          </div>
          {/* NIIRS Tasks */}
          <div className="mt-3 pt-3 border-t border-white/[0.06]">
            <div className="text-[10px] text-white/40 mb-1.5">Achievable at this NIIRS level:</div>
            <div className="space-y-1">
              {result.niirs_interpretation.tasks.slice(0, 4).map((task, i) => (
                <div key={i} className="flex items-start gap-1.5">
                  <div className="w-1 h-1 rounded-full bg-gorzen-400 mt-1.5 flex-shrink-0" />
                  <span className="text-[10px] text-white/60">{task}</span>
                </div>
              ))}
            </div>
          </div>
        </GlassPanel>
      )}

      {/* Model Stages */}
      {result && PHASE_GROUPS.map(phase => (
        <GlassPanel key={phase.label} padding="p-3">
          <div className="flex items-center gap-2 mb-2 px-1">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: phase.color }} />
            <h3 className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: phase.color + 'aa' }}>
              {phase.label}
            </h3>
          </div>
          <div className="space-y-1.5">
            {phase.stages.map(stageKey => {
              const meta = STAGE_META.find(s => s.key === stageKey);
              return (
                <StageCard
                  key={stageKey}
                  stageKey={stageKey}
                  label={meta?.label || stageKey}
                  color={phase.color}
                  data={result.stages[stageKey]}
                  expanded={expanded.has(stageKey)}
                  onToggle={() => toggleStage(stageKey)}
                />
              );
            })}
          </div>
        </GlassPanel>
      ))}
    </div>
  );
}
