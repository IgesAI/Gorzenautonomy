import React from 'react';
import type { EnvelopeOutput } from '../../types/envelope';
import { getConfidenceColor } from '../../theme/tokens';

interface BatteryReserveProps {
  output?: EnvelopeOutput | null;
}

export function BatteryReserve({ output }: BatteryReserveProps) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
        Battery Reserve (VTOL)
      </h3>
      {!output ? (
        <div className="h-16 flex items-center justify-center text-white/20 text-sm">
          No data
        </div>
      ) : (
        <div>
          <div className="flex items-baseline gap-2 mb-3">
            <span className="text-2xl font-bold font-mono" style={{ color: getConfidenceColor(Math.min(output.mean / 40, 1)) }}>
              {output.mean.toFixed(1)}
            </span>
            <span className="text-xs text-white/40">{output.units || 'min'}</span>
            <span className="text-xs text-white/30 font-mono ml-auto">
              {'\u00B1'}{output.std.toFixed(1)}
            </span>
          </div>

          {/* Range bar: scale to 60 min */}
          <div className="relative h-6 bg-white/5 rounded-lg overflow-hidden mb-1">
            <div
              className="absolute h-full bg-gorzen-500/15 rounded-lg"
              style={{
                left: `${Math.max(0, (output.percentiles.p5 ?? 0) / 60 * 100)}%`,
                width: `${Math.min(100, ((output.percentiles.p95 ?? output.mean) - (output.percentiles.p5 ?? 0)) / 60 * 100)}%`,
              }}
            />
            <div
              className="absolute top-0 h-full w-0.5 bg-gorzen-400"
              style={{ left: `${Math.min(100, (output.percentiles.p50 ?? output.mean) / 60 * 100)}%` }}
            />
            {[0, 15, 30, 45, 60].map((m) => (
              <div key={m} className="absolute top-0 h-full w-px bg-white/5" style={{ left: `${m / 60 * 100}%` }} />
            ))}
          </div>

          <div className="flex justify-between text-[10px] font-mono">
            <span className="text-red-400/60">P5: {(output.percentiles.p5 ?? 0).toFixed(1)}</span>
            <span className="text-gorzen-400/80">P50: {(output.percentiles.p50 ?? output.mean).toFixed(1)}</span>
            <span className="text-emerald-400/60">P95: {(output.percentiles.p95 ?? 0).toFixed(1)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
