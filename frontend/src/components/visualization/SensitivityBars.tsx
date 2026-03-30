import type { SensitivityEntry } from '../../types/envelope';
import { chartStyles } from '../../theme/chartStyles';

interface SensitivityBarsProps {
  entries: SensitivityEntry[];
}

const PARAM_LABELS: Record<string, string> = {
  wind_speed_ms: 'Wind Speed',
  bsfc_cruise_g_kwh: 'Fuel Consumption (BSFC)',
  mass_total_kg: 'Vehicle Mass',
  cd0: 'Parasitic Drag Coeff.',
  soh_pct: 'Battery Health (SoH)',
  temperature_c: 'Temperature',
  encoding_bitrate_mbps: 'Encoding Bitrate',
  fuel_reserve_pct: 'Fuel Reserve Policy',
  exposure_time_s: 'Shutter Exposure Time',
  'airspeed_ms': 'Airspeed → Ident. Confidence',
  'altitude_m': 'Altitude → Ident. Confidence',
  'airspeed_ms (endurance)': 'Airspeed → Fuel Endurance',
  'altitude_m (endurance)': 'Altitude → Fuel Endurance',
  lens_mtf_nyquist: 'Lens Quality (MTF)',
};

const TARGET_COLORS: Record<string, string> = {
  'airspeed_ms': '#38bdf8',
  'altitude_m': '#38bdf8',
  'airspeed_ms (endurance)': '#f59e0b',
  'altitude_m (endurance)': '#f59e0b',
};

function getTargetFromName(name: string): string {
  if (name.includes('endurance')) return 'endurance';
  return 'identification';
}

export function SensitivityBars({ entries }: SensitivityBarsProps) {
  const sorted = [...entries]
    .sort((a, b) => b.contribution_pct - a.contribution_pct)
    .slice(0, 8);
  const maxPct = Math.max(...sorted.map((e) => e.contribution_pct), 1);

  const identEntries = sorted.filter((e) => getTargetFromName(e.parameter_name) === 'identification');
  const endurEntries = sorted.filter((e) => getTargetFromName(e.parameter_name) === 'endurance');

  const renderGroup = (title: string, color: string, items: SensitivityEntry[]) => {
    if (items.length === 0) return null;
    return (
      <div className="mb-4 last:mb-0">
        <div className="flex items-center gap-2 mb-2.5">
          <div className="w-2 h-2 rounded-full" style={{ background: color }} />
          <span className="text-[10px] font-semibold text-white/50 uppercase tracking-wider">{title}</span>
        </div>
        <div className="space-y-2.5">
          {items.map((entry) => {
            const label = PARAM_LABELS[entry.parameter_name] ?? entry.parameter_name.replace(/_/g, ' ');
            const widthPct = (entry.contribution_pct / maxPct) * 100;
            const entryColor = TARGET_COLORS[entry.parameter_name] ?? color;
            return (
              <div key={entry.parameter_name}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-white/60 truncate pr-2 max-w-[75%]">{label}</span>
                  <span className="text-[10px] text-white/45 font-mono tabular-nums flex-shrink-0">
                    {entry.contribution_pct.toFixed(1)}%
                  </span>
                </div>
                <div className="relative h-4 bg-white/[0.03] rounded overflow-hidden">
                  <div
                    className="absolute left-0 top-0 h-full rounded transition-all duration-500 ease-out"
                    style={{
                      width: `${widthPct}%`,
                      background: `${entryColor}60`,
                      boxShadow: `inset 0 0 0 1px ${entryColor}30`,
                    }}
                  />
                  {entry.sobol_first_order != null && (
                    <div
                      className="absolute left-0 top-0 h-full rounded"
                      style={{
                        width: `${(entry.sobol_first_order / maxPct) * 10000}%`,
                        background: `${entryColor}90`,
                      }}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div>
      <h3 className={`${chartStyles.title} mb-1`}>Sensitivity Analysis</h3>
      <p className="text-[9px] text-white/30 mb-4">
        Correlation strength between input parameters and key outputs
      </p>

      {sorted.length === 0 ? (
        <div className={chartStyles.emptyState}>
          No sensitivity data available
        </div>
      ) : (
        <>
          {renderGroup('Identification Confidence', '#38bdf8', identEntries)}
          {renderGroup('Fuel Endurance', '#f59e0b', endurEntries)}

          {/* Ungrouped fallback */}
          {identEntries.length === 0 && endurEntries.length === 0 && (
            <div className="space-y-2.5">
              {sorted.map((entry) => {
                const label = PARAM_LABELS[entry.parameter_name] ?? entry.parameter_name.replace(/_/g, ' ');
                const widthPct = (entry.contribution_pct / maxPct) * 100;
                return (
                  <div key={entry.parameter_name}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] text-white/60 truncate pr-2 max-w-[75%]">{label}</span>
                      <span className="text-[10px] text-white/45 font-mono tabular-nums flex-shrink-0">
                        {entry.contribution_pct.toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-4 bg-white/[0.03] rounded overflow-hidden">
                      <div
                        className="h-full rounded transition-all duration-500 ease-out"
                        style={{
                          width: `${widthPct}%`,
                          background: 'rgba(56, 189, 248, 0.4)',
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      <p className="text-[8px] text-white/25 mt-3 leading-relaxed">
        Higher % = stronger correlation. Bars show absolute Pearson correlation between the parameter and
        the target metric across the full speed-altitude grid.
      </p>
    </div>
  );
}
