import React from 'react';
import type { EnvelopeOutput } from '../../types/envelope';
import { chartStyles } from '../../theme/chartStyles';
import { colors } from '../../theme/tokens';

interface BatteryReserveProps {
  output?: EnvelopeOutput | null;
}

function getBarColor(mean: number, scaleMax: number): string {
  const ratio = mean / scaleMax;
  if (ratio >= 0.5) return `${colors.status.success}99`;
  if (ratio >= 0.25) return `${colors.status.warning}99`;
  return `${colors.status.danger}99`;
}

export function BatteryReserve({ output }: BatteryReserveProps) {
  if (!output) {
    return (
      <div>
        <h3 className={chartStyles.title}>Battery Reserve (VTOL)</h3>
        <div className={chartStyles.emptyState}>No data</div>
      </div>
    );
  }

  const p5 = output.percentiles.p5 ?? output.mean - output.std;
  const p50 = output.percentiles.p50 ?? output.mean;
  const p95 = output.percentiles.p95 ?? output.mean + output.std;
  const scaleMax = Math.max(p95 * 1.2, 30, 60);
  const leftPct = Math.max(0, (p5 / scaleMax) * 100);
  const widthPct = Math.min(100 - leftPct, ((p95 - p5) / scaleMax) * 100);
  const medianPct = Math.min(100, (p50 / scaleMax) * 100);

  return (
    <div>
      <h3 className={`${chartStyles.title} mb-1`}>Battery Reserve (VTOL)</h3>
      <p className="text-[9px] text-white/40 mb-3">At nominal operating point (Monte Carlo)</p>

      <div className="flex items-baseline gap-2 mb-3">
        <span className={`${chartStyles.valuePrimary}`} style={{ color: getBarColor(output.mean, scaleMax) }}>
          {output.mean.toFixed(1)}
        </span>
        <span className={chartStyles.valueSecondary}>{output.units || 'min'}</span>
        <span className="text-[10px] text-white/40 font-mono ml-auto">
          ±{output.std.toFixed(1)}
        </span>
      </div>

      <div className="relative h-7 bg-white/[0.04] rounded-lg overflow-hidden mb-2">
        <div
          className="absolute h-full rounded-lg transition-all duration-300"
          style={{
            left: `${leftPct}%`,
            width: `${Math.max(widthPct, 2)}%`,
            background: getBarColor(output.mean, scaleMax),
          }}
        />
        <div
          className="absolute top-0 h-full w-0.5 bg-white/90"
          style={{ left: `${medianPct}%` }}
        />
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <div
            key={t}
            className="absolute top-0 h-full w-px bg-white/10"
            style={{ left: `${t * 100}%` }}
          />
        ))}
      </div>

      <div className="flex justify-between text-[10px] font-mono text-white/50">
        <span>P5: {p5.toFixed(1)}</span>
        <span className="text-white/70">P50: {p50.toFixed(1)}</span>
        <span>P95: {p95.toFixed(1)}</span>
      </div>
      <div className="text-[9px] text-white/35 mt-1 font-mono">
        0 — {scaleMax.toFixed(0)} {output.units || 'min'}
      </div>
    </div>
  );
}
