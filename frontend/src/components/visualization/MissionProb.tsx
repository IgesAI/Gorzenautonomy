import React from 'react';
import { getConfidenceColor } from '../../theme/tokens';

interface MissionProbProps {
  probability?: number | null;
}

export function MissionProb({ probability }: MissionProbProps) {
  const p = probability ?? 0;
  const pct = p * 100;
  const circumference = 2 * Math.PI * 40;
  const offset = circumference * (1 - p);
  const color = getConfidenceColor(p);

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
        Mission Completion Probability
      </h3>
      <div className="flex items-center gap-4">
        <div className="relative w-24 h-24 flex-shrink-0">
          <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
            <circle
              cx="50" cy="50" r="40"
              fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="8"
            />
            <circle
              cx="50" cy="50" r="40"
              fill="none" stroke={color} strokeWidth="8"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              strokeLinecap="round"
              className="transition-all duration-700"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-lg font-bold font-mono" style={{ color }}>
              {probability != null ? `${pct.toFixed(0)}%` : '--'}
            </span>
          </div>
        </div>
        <div className="text-xs text-white/50 space-y-1">
          <div>Energy + reserve: <span className="text-white/70">OK</span></div>
          <div>Perception quality: <span className="text-white/70">OK</span></div>
          <div>Compute latency: <span className="text-white/70">OK</span></div>
          <div>Comms link: <span className="text-white/70">OK</span></div>
        </div>
      </div>
    </div>
  );
}
