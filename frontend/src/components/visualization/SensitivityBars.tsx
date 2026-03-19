import React from 'react';
import type { SensitivityEntry } from '../../types/envelope';

interface SensitivityBarsProps {
  entries: SensitivityEntry[];
}

const PARAM_LABELS: Record<string, string> = {
  wind_speed_ms: 'Wind Speed',
  bsfc_cruise_g_kwh: 'Fuel Consumption (BSFC)',
  mass_total_kg: 'Vehicle Mass',
  cd0: 'Parasitic Drag',
  soh_pct: 'Battery Health (SoH)',
  temperature_c: 'Temperature',
  fuel_reserve_pct: 'Fuel Reserve',
  exposure_time_s: 'Exposure Time',
};

const BAR_COLORS = [
  'rgba(47, 127, 255, 0.7)',
  'rgba(47, 127, 255, 0.55)',
  'rgba(47, 127, 255, 0.42)',
  'rgba(47, 127, 255, 0.32)',
  'rgba(47, 127, 255, 0.24)',
  'rgba(47, 127, 255, 0.18)',
  'rgba(47, 127, 255, 0.14)',
  'rgba(47, 127, 255, 0.10)',
];

export function SensitivityBars({ entries }: SensitivityBarsProps) {
  const sorted = [...entries].sort((a, b) => b.contribution_pct - a.contribution_pct).slice(0, 8);
  const maxPct = Math.max(...sorted.map((e) => e.contribution_pct), 1);

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
        Uncertainty Contributors
      </h3>
      {sorted.length === 0 ? (
        <div className="h-20 flex items-center justify-center text-white/20 text-sm">
          No sensitivity data
        </div>
      ) : (
        <div className="space-y-2">
          {sorted.map((entry, i) => {
            const label = PARAM_LABELS[entry.parameter_name] ?? entry.parameter_name.replace(/_/g, ' ');
            const widthPct = (entry.contribution_pct / maxPct) * 100;
            return (
              <div key={entry.parameter_name}>
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-[11px] text-white/60 truncate pr-2" style={{ maxWidth: '65%' }}>
                    {label}
                  </span>
                  <span className="text-[10px] text-white/40 font-mono flex-shrink-0">
                    {entry.contribution_pct.toFixed(1)}%
                  </span>
                </div>
                <div className="h-4 bg-white/5 rounded overflow-hidden">
                  <div
                    className="h-full rounded transition-all duration-700 ease-out"
                    style={{
                      width: `${widthPct}%`,
                      background: BAR_COLORS[i] ?? BAR_COLORS[BAR_COLORS.length - 1],
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
