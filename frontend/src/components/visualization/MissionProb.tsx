import { AlertTriangle, Clock } from 'lucide-react';
import { chartStyles } from '../../theme/chartStyles';

interface MissionProbProps {
  probability?: number | null;
  warnings?: string[];
  computeTimeS?: number;
  feasiblePct?: number;
  gridSize?: string;
}

function getRisk(p: number) {
  if (p >= 0.9) return { label: 'Viable', color: '#10b981', bg: 'bg-emerald-500/10', text: 'text-emerald-400', ring: 'ring-emerald-500/20' };
  if (p >= 0.7) return { label: 'Marginal', color: '#f59e0b', bg: 'bg-amber-500/10', text: 'text-amber-400', ring: 'ring-amber-500/20' };
  if (p >= 0.5) return { label: 'Elevated Risk', color: '#f97316', bg: 'bg-orange-500/10', text: 'text-orange-400', ring: 'ring-orange-500/20' };
  return { label: 'Not Viable', color: '#ef4444', bg: 'bg-red-500/10', text: 'text-red-400', ring: 'ring-red-500/20' };
}

export function MissionProb({ probability, warnings, computeTimeS, feasiblePct, gridSize }: MissionProbProps) {
  const hasData = probability != null;
  const p = probability ?? 0;
  const pct = p * 100;
  const risk = getRisk(p);

  return (
    <div>
      <div className="flex items-center justify-between">
        <h3 className={chartStyles.title}>Mission Completion Probability</h3>
        {computeTimeS != null && (
          <div className="flex items-center gap-1 text-[9px] text-white/25 font-mono">
            <Clock size={9} />
            {computeTimeS.toFixed(1)}s
          </div>
        )}
      </div>

      {hasData ? (
        <div className="mt-3">
          {/* Main readout */}
          <div className="flex items-baseline gap-3 mb-3">
            <span className="text-3xl font-bold font-mono tabular-nums tracking-tight" style={{ color: risk.color }}>
              {pct.toFixed(1)}
            </span>
            <span className="text-sm text-white/25 font-medium">%</span>
            <span className={`ml-auto text-[10px] font-semibold px-2.5 py-1 rounded-md ${risk.bg} ${risk.text} uppercase tracking-wider`}>
              {risk.label}
            </span>
          </div>

          {/* Progress bar */}
          <div className="h-2.5 rounded-full bg-white/[0.04] overflow-hidden relative">
            <div
              className="h-full rounded-full transition-all duration-700 ease-out"
              style={{
                width: `${pct}%`,
                backgroundColor: risk.color,
                boxShadow: `0 0 10px ${risk.color}30`,
              }}
            />
            {/* Zone markers */}
            {[50, 70, 90].map((t) => (
              <div
                key={t}
                className="absolute top-0 h-full w-px bg-white/10"
                style={{ left: `${t}%` }}
              />
            ))}
          </div>

          {/* Scale with zone labels */}
          <div className="flex justify-between mt-1.5 text-[8px] font-mono text-white/20">
            <span>0</span>
            <span className="text-red-400/40">Not Viable</span>
            <span className="text-orange-400/40">Risk</span>
            <span className="text-amber-400/40">Marginal</span>
            <span className="text-emerald-400/40">Viable</span>
            <span>100</span>
          </div>

          {/* Breakdown stats */}
          {(feasiblePct != null || gridSize) && (
            <div className="mt-3 pt-3 border-t border-white/[0.05] space-y-1.5">
              {feasiblePct != null && (
                <div className="flex justify-between text-[10px]">
                  <span className="text-white/40">Grid cells feasible</span>
                  <span className="font-mono text-white/60">{feasiblePct.toFixed(0)}%</span>
                </div>
              )}
              {gridSize && (
                <div className="flex justify-between text-[10px]">
                  <span className="text-white/40">Grid resolution</span>
                  <span className="font-mono text-white/60">{gridSize}</span>
                </div>
              )}
            </div>
          )}

          <p className="text-[9px] text-white/25 mt-3 leading-relaxed">
            Fraction of speed–altitude grid that is both aerodynamically feasible and meets the
            minimum identification confidence threshold (80%).
          </p>
        </div>
      ) : (
        <div className="mt-3 py-6 text-center">
          <div className="text-[11px] text-white/25">
            Click <span className="text-white/45 font-medium">"Compute Envelope"</span> to evaluate
          </div>
        </div>
      )}

      {/* Warnings */}
      {warnings && warnings.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 px-2.5 py-1.5 rounded-md bg-amber-500/[0.06] border border-amber-500/10">
              <AlertTriangle size={10} className="text-amber-400/60 mt-0.5 flex-shrink-0" />
              <span className="text-[9px] text-amber-400/70 leading-relaxed">{w}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
