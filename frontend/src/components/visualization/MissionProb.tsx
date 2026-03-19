import React from 'react';
import { getConfidenceColor } from '../../theme/tokens';

interface MissionProbProps {
  probability?: number | null;
  warnings?: string[];
}

export function MissionProb({ probability, warnings }: MissionProbProps) {
  const p = probability ?? 0;
  const pct = p * 100;
  const circumference = 2 * Math.PI * 40;
  const offset = circumference * (1 - p);
  const color = getConfidenceColor(p);

  const riskLevel = p >= 0.9 ? 'LOW RISK' : p >= 0.7 ? 'MODERATE' : p >= 0.5 ? 'ELEVATED' : 'HIGH RISK';
  const riskColor = p >= 0.9 ? 'text-emerald-400' : p >= 0.7 ? 'text-yellow-400' : p >= 0.5 ? 'text-orange-400' : 'text-red-400';

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
        Mission Completion Probability
      </h3>
      <div className="flex items-center gap-5">
        <div className="relative w-28 h-28 flex-shrink-0">
          <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
            <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="7" />
            {probability != null && (
              <circle
                cx="50" cy="50" r="40"
                fill="none" stroke={color} strokeWidth="7"
                strokeDasharray={circumference}
                strokeDashoffset={offset}
                strokeLinecap="round"
                className="transition-all duration-1000 ease-out"
              />
            )}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-xl font-bold font-mono" style={{ color }}>
              {probability != null ? `${pct.toFixed(1)}%` : '--'}
            </span>
            {probability != null && (
              <span className={`text-[9px] font-semibold ${riskColor}`}>{riskLevel}</span>
            )}
          </div>
        </div>
        <div className="flex-1 text-[11px] text-white/50 space-y-1.5">
          <div className="flex justify-between">
            <span>Energy + reserves</span>
            <span className="font-mono text-emerald-400/80">{probability != null ? 'PASS' : '--'}</span>
          </div>
          <div className="flex justify-between">
            <span>Perception quality</span>
            <span className="font-mono text-emerald-400/80">{probability != null ? 'PASS' : '--'}</span>
          </div>
          <div className="flex justify-between">
            <span>Engine feasibility</span>
            <span className="font-mono text-emerald-400/80">{probability != null ? 'PASS' : '--'}</span>
          </div>
          <div className="flex justify-between">
            <span>Comms link</span>
            <span className="font-mono text-emerald-400/80">{probability != null ? 'PASS' : '--'}</span>
          </div>
        </div>
      </div>
      {warnings && warnings.length > 0 && (
        <div className="mt-3 pt-2 border-t border-white/5">
          {warnings.map((w, i) => (
            <div key={i} className="text-[10px] text-yellow-400/70 flex items-start gap-1.5">
              <span className="mt-0.5">{'!'}</span>
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
