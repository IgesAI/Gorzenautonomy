import React from 'react';
import type { EnvelopeOutput } from '../../types/envelope';
import { chartStyles } from '../../theme/chartStyles';

interface FuelEnduranceProps {
  output?: EnvelopeOutput | null;
  flowRate?: EnvelopeOutput | null;
}

function getEnduranceColor(hr: number): string {
  if (hr >= 4) return 'rgba(16,185,129,0.9)';
  if (hr >= 2) return 'rgba(245,158,11,0.9)';
  return 'rgba(239,68,68,0.9)';
}

export function FuelEndurance({ output, flowRate }: FuelEnduranceProps) {
  if (!output) {
    return (
      <div>
        <h3 className={chartStyles.title}>Fuel Endurance</h3>
        <div className={chartStyles.emptyState}>No data</div>
      </div>
    );
  }

  const p5 = output.percentiles.p5 ?? output.mean - output.std;
  const p50 = output.percentiles.p50 ?? output.mean;
  const p95 = output.percentiles.p95 ?? output.mean + output.std;
  const scaleMax = Math.max(p95 * 1.15, 8, 20);
  const leftPct = Math.max(0, (p5 / scaleMax) * 100);
  const widthPct = Math.min(100 - leftPct, ((p95 - p5) / scaleMax) * 100);
  const medianPct = Math.min(100, (p50 / scaleMax) * 100);

  return (
    <div>
      <h3 className={`${chartStyles.title} mb-1`}>Fuel Endurance</h3>
      <p className="text-[9px] text-white/40 mb-3">At nominal operating point (Monte Carlo)</p>

      <div className="flex items-baseline gap-2 mb-3">
        <span className={chartStyles.valuePrimary} style={{ color: getEnduranceColor(output.mean) }}>
          {output.mean.toFixed(1)}
        </span>
        <span className={chartStyles.valueSecondary}>hr</span>
        <span className="text-[10px] text-white/40 font-mono ml-auto">
          ±{output.std.toFixed(2)} hr
        </span>
      </div>

      <div className="relative h-8 bg-white/[0.04] rounded-lg overflow-hidden mb-2">
        <div
          className="absolute h-full rounded-lg transition-all duration-300"
          style={{
            left: `${leftPct}%`,
            width: `${Math.max(widthPct, 2)}%`,
            background: 'linear-gradient(90deg, rgba(239,68,68,0.4), rgba(16,185,129,0.5))',
          }}
        />
        <div
          className="absolute top-0 h-full w-0.5 bg-white/90"
          style={{ left: `${medianPct}%` }}
        />
        {[0, 4, 8, 12, 16, 20].filter((h) => h <= scaleMax).map((h) => (
          <div
            key={h}
            className="absolute top-0 h-full w-px bg-white/10"
            style={{ left: `${(h / scaleMax) * 100}%` }}
          />
        ))}
      </div>

      <div className="flex justify-between text-[10px] font-mono text-white/50">
        <span>P5: {p5.toFixed(1)}h</span>
        <span className="text-white/70">P50: {p50.toFixed(1)}h</span>
        <span>P95: {p95.toFixed(1)}h</span>
      </div>

      {flowRate && (
        <div className="mt-4 pt-3 border-t border-white/10 space-y-2">
          <div className="flex justify-between text-[11px]">
            <span className="text-white/60">Fuel flow rate</span>
            <span className="font-mono text-white/90">{flowRate.mean.toFixed(0)} g/hr</span>
          </div>
          <div className="flex justify-between text-[10px] text-white/45">
            <span>Range (P5–P95)</span>
            <span className="font-mono">
              {(flowRate.percentiles.p5 ?? 0).toFixed(0)} – {(flowRate.percentiles.p95 ?? 0).toFixed(0)} g/hr
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
