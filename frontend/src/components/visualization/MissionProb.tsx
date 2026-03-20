import { AlertTriangle } from 'lucide-react';
import { chartStyles } from '../../theme/chartStyles';

interface MissionProbProps {
  probability?: number | null;
  warnings?: string[];
}

function getRisk(p: number) {
  if (p >= 0.9) return { label: 'Viable', color: '#10b981', bg: 'bg-emerald-500/10', text: 'text-emerald-400' };
  if (p >= 0.7) return { label: 'Marginal', color: '#f59e0b', bg: 'bg-amber-500/10', text: 'text-amber-400' };
  if (p >= 0.5) return { label: 'Elevated Risk', color: '#f97316', bg: 'bg-orange-500/10', text: 'text-orange-400' };
  return { label: 'Not Viable', color: '#ef4444', bg: 'bg-red-500/10', text: 'text-red-400' };
}

export function MissionProb({ probability, warnings }: MissionProbProps) {
  const hasData = probability != null;
  const p = probability ?? 0;
  const pct = p * 100;
  const risk = getRisk(p);

  return (
    <div>
      <h3 className={chartStyles.title}>Mission Completion</h3>

      {hasData ? (
        <div className="mt-3">
          {/* Main readout */}
          <div className="flex items-baseline gap-3 mb-3">
            <span className="text-3xl font-bold font-mono tabular-nums tracking-tight" style={{ color: risk.color }}>
              {pct.toFixed(1)}
            </span>
            <span className="text-sm text-white/30 font-medium">%</span>
            <span className={`ml-auto text-[10px] font-semibold px-2.5 py-1 rounded-md ${risk.bg} ${risk.text} uppercase tracking-wider`}>
              {risk.label}
            </span>
          </div>

          {/* Progress bar */}
          <div className="h-2 rounded-full bg-white/[0.06] overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700 ease-out"
              style={{
                width: `${pct}%`,
                backgroundColor: risk.color,
                boxShadow: `0 0 8px ${risk.color}40`,
              }}
            />
          </div>

          {/* Scale markers */}
          <div className="flex justify-between mt-1.5 text-[9px] font-mono text-white/20">
            <span>0</span>
            <span>25</span>
            <span>50</span>
            <span>75</span>
            <span>100</span>
          </div>

          <p className="text-[10px] text-white/35 mt-3 leading-relaxed">
            Fraction of speed-altitude grid that is feasible and meets minimum identification confidence.
          </p>
        </div>
      ) : (
        <div className="mt-3 py-4 text-center">
          <div className="text-[11px] text-white/30">
            Run <span className="text-white/50 font-medium">Compute Envelope</span> to evaluate
          </div>
        </div>
      )}

      {warnings && warnings.length > 0 && (
        <div className="mt-3 space-y-1">
          {warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 px-2.5 py-1.5 rounded-md bg-amber-500/[0.07] border border-amber-500/15">
              <AlertTriangle size={10} className="text-amber-400/70 mt-0.5 flex-shrink-0" />
              <span className="text-[10px] text-amber-400/80 leading-relaxed">{w}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
