import React from 'react';
import { Target } from 'lucide-react';
import { chartStyles } from '../../theme/chartStyles';
import { colors } from '../../theme/tokens';

interface MissionProbProps {
  probability?: number | null;
  warnings?: string[];
}

function getRiskStyle(p: number): { label: string; color: string; bg: string } {
  if (p >= 0.9) return { label: 'Mission viable', color: 'text-emerald-400', bg: 'bg-emerald-500/15' };
  if (p >= 0.7) return { label: 'Marginal', color: 'text-amber-400', bg: 'bg-amber-500/15' };
  if (p >= 0.5) return { label: 'Elevated risk', color: 'text-orange-400', bg: 'bg-orange-500/15' };
  return { label: 'Not viable', color: 'text-red-400', bg: 'bg-red-500/15' };
}

function getDialColor(p: number): string {
  if (p >= 0.8) return colors.status.success;
  if (p >= 0.5) return colors.status.warning;
  return colors.status.danger;
}

export function MissionProb({ probability, warnings }: MissionProbProps) {
  const hasData = probability != null;
  const p = probability ?? 0;
  const pct = p * 100;
  const circumference = 2 * Math.PI * 42;
  const offset = circumference * (1 - p);
  const dialColor = getDialColor(p);
  const risk = getRiskStyle(p);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className={chartStyles.title}>Mission Completion Probability</h3>
        {hasData && (
          <span className={`text-[9px] font-medium px-2 py-0.5 rounded-full ${risk.bg} ${risk.color}`}>
            {risk.label}
          </span>
        )}
      </div>

      <div className="flex items-start gap-5">
        <div className="relative w-28 h-28 flex-shrink-0">
          <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90 drop-shadow-lg">
            {/* Track */}
            <circle
              cx="50"
              cy="50"
              r="42"
              fill="none"
              stroke="rgba(255,255,255,0.08)"
              strokeWidth="10"
            />
            {/* Progress arc */}
            {hasData && (
              <circle
                cx="50"
                cy="50"
                r="42"
                fill="none"
                stroke={dialColor}
                strokeWidth="10"
                strokeDasharray={circumference}
                strokeDashoffset={offset}
                strokeLinecap="round"
                className="transition-all duration-700 ease-out"
                style={{ filter: `drop-shadow(0 0 6px ${dialColor}40)` }}
              />
            )}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            {hasData ? (
              <>
                <span
                  className="text-2xl font-bold font-mono tabular-nums tracking-tight"
                  style={{ color: dialColor }}
                >
                  {pct.toFixed(1)}%
                </span>
                <span className="text-[9px] text-white/40 font-medium mt-1">P(success)</span>
              </>
            ) : (
              <div className="flex flex-col items-center gap-1">
                <Target className="w-8 h-8 text-white/20" strokeWidth={1.5} />
                <span className="text-[10px] text-white/35 text-center">Compute envelope</span>
              </div>
            )}
          </div>
        </div>

        <div className="flex-1 min-w-0 pt-0.5">
          <p className="text-[11px] text-white/55 leading-relaxed">
            {hasData ? (
              <>
                Fraction of the speed–altitude envelope that is <strong className="text-white/70">feasible</strong> and meets your{' '}
                <strong className="text-white/70">min identification confidence</strong>. Varies with your inputs (wind, sensor, compute, etc.).
              </>
            ) : (
              'Run "Compute Envelope" to evaluate mission viability at the nominal operating point.'
            )}
          </p>
          {hasData && (
            <p className="text-[9px] text-white/35 mt-2 leading-relaxed">
              % of grid points (feasible × ident ≥ min). Raise min confidence to see it drop.
            </p>
          )}
          {warnings && warnings.length > 0 && (
            <div className="mt-3 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 space-y-1.5">
              {warnings.map((w, i) => (
                <div key={i} className="text-[10px] text-amber-400/90 flex items-start gap-2">
                  <span className="flex-shrink-0 mt-0.5">⚠</span>
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
