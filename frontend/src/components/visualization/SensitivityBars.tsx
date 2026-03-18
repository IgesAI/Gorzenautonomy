import React from 'react';
import type { SensitivityEntry } from '../../types/envelope';

interface SensitivityBarsProps {
  entries: SensitivityEntry[];
}

export function SensitivityBars({ entries }: SensitivityBarsProps) {
  const sorted = [...entries].sort((a, b) => b.contribution_pct - a.contribution_pct).slice(0, 8);
  const maxPct = Math.max(...sorted.map((e) => e.contribution_pct), 1);

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
        Uncertainty Contributors
      </h3>
      {sorted.length === 0 ? (
        <div className="h-16 flex items-center justify-center text-white/20 text-sm">
          No sensitivity data
        </div>
      ) : (
        <div className="space-y-2">
          {sorted.map((entry) => (
            <div key={entry.parameter_name} className="flex items-center gap-2">
              <span className="text-[10px] text-white/50 w-32 truncate font-mono">
                {entry.parameter_name}
              </span>
              <div className="flex-1 h-3 bg-white/5 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gorzen-500/60 rounded-full transition-all duration-500"
                  style={{ width: `${(entry.contribution_pct / maxPct) * 100}%` }}
                />
              </div>
              <span className="text-[10px] text-white/40 font-mono w-10 text-right">
                {entry.contribution_pct.toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
