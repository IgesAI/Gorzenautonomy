import React from 'react';
import type { SensitivityEntry } from '../../types/envelope';
import { chartStyles } from '../../theme/chartStyles';

interface SensitivityBarsProps {
  entries: SensitivityEntry[];
}

const PARAM_LABELS: Record<string, string> = {
  wind_speed_ms: 'Wind speed',
  bsfc_cruise_g_kwh: 'Fuel consumption (BSFC)',
  mass_total_kg: 'Vehicle mass',
  cd0: 'Parasitic drag',
  soh_pct: 'Battery health (SoH)',
  temperature_c: 'Temperature',
  encoding_bitrate_mbps: 'Encoding bitrate',
  fuel_reserve_pct: 'Fuel reserve',
  exposure_time_s: 'Exposure time',
};

export function SensitivityBars({ entries }: SensitivityBarsProps) {
  const sorted = [...entries]
    .sort((a, b) => b.contribution_pct - a.contribution_pct)
    .slice(0, 8);
  const maxPct = Math.max(...sorted.map((e) => e.contribution_pct), 1);

  return (
    <div>
      <h3 className={`${chartStyles.title} mb-4`}>Uncertainty Contributors</h3>

      {sorted.length === 0 ? (
        <div className={chartStyles.emptyState}>No sensitivity data</div>
      ) : (
        <div className="space-y-3">
          {sorted.map((entry, i) => {
            const label = PARAM_LABELS[entry.parameter_name] ?? entry.parameter_name.replace(/_/g, ' ');
            const widthPct = (entry.contribution_pct / maxPct) * 100;
            const opacity = 1 - i * 0.08;
            return (
              <div key={entry.parameter_name}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] text-white/70 truncate pr-2 max-w-[70%]">{label}</span>
                  <span className="text-[10px] text-white/50 font-mono tabular-nums flex-shrink-0">
                    {entry.contribution_pct.toFixed(1)}%
                  </span>
                </div>
                <div className="h-5 bg-white/[0.04] rounded-md overflow-hidden">
                  <div
                    className="h-full rounded-md transition-all duration-500 ease-out"
                    style={{
                      width: `${widthPct}%`,
                      background: `rgba(47, 127, 255, ${opacity * 0.6})`,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      <p className="text-[9px] text-white/35 mt-3 leading-relaxed">
        Parameters ranked by correlation with mission constraints (fuel endurance, identification confidence) at nominal operating point.
      </p>
    </div>
  );
}
