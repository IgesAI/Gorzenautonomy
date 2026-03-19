import React from 'react';
import { chartStyles } from '../../theme/chartStyles';

interface MissionProbProps {
  probability?: number | null;
  warnings?: string[];
}

function getRiskStyle(p: number): { label: string; color: string } {
  if (p >= 0.9) return { label: 'Low risk', color: 'text-emerald-400' };
  if (p >= 0.7) return { label: 'Moderate', color: 'text-amber-400' };
  if (p >= 0.5) return { label: 'Elevated', color: 'text-orange-400' };
  return { label: 'High risk', color: 'text-red-400' };
}

function getDialColor(p: number): string {
  if (p >= 0.8) return '#10b981';
  if (p >= 0.5) return '#f59e0b';
  return '#ef4444';
}

export function MissionProb({ probability, warnings }: MissionProbProps) {
  const p = probability ?? 0;
  const pct = p * 100;
  const circumference = 2 * Math.PI * 42;
  const offset = circumference * (1 - p);
  const dialColor = getDialColor(p);
  const risk = getRiskStyle(p);

  return (
    <div>
      <h3 className={`${chartStyles.title} mb-4`}>Mission Completion Probability</h3>

      <div className="flex items-start gap-6">
        <div className="relative w-24 h-24 flex-shrink-0">
          <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
            <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
            {probability != null && (
              <circle
                cx="50"
                cy="50"
                r="42"
                fill="none"
                stroke={dialColor}
                strokeWidth="8"
                strokeDasharray={circumference}
                strokeDashoffset={offset}
                strokeLinecap="round"
                className="transition-all duration-700 ease-out"
              />
            )}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-bold font-mono tabular-nums" style={{ color: dialColor }}>
              {probability != null ? `${pct.toFixed(1)}%` : '—'}
            </span>
            {probability != null && (
              <span className={`text-[10px] font-medium mt-0.5 ${risk.color}`}>{risk.label}</span>
            )}
          </div>
        </div>

        <div className="flex-1 min-w-0 pt-1">
          <p className="text-[11px] text-white/55 leading-relaxed">
            Probability that fuel endurance and identification confidence meet mission constraints under uncertainty.
            <span className="block mt-1 text-white/40">Evaluated at nominal operating point (center of speed/altitude range).</span>
          </p>
          {warnings && warnings.length > 0 && (
            <div className="mt-3 space-y-1.5">
              {warnings.map((w, i) => (
                <div key={i} className="text-[10px] text-amber-400/80 flex items-start gap-2">
                  <span className="flex-shrink-0">⚠</span>
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
