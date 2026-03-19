import React from 'react';
import type { EnvelopeOutput } from '../../types/envelope';
import { getConfidenceColor } from '../../theme/tokens';

interface FuelEnduranceProps {
  output?: EnvelopeOutput | null;
  flowRate?: EnvelopeOutput | null;
}

export function FuelEndurance({ output, flowRate }: FuelEnduranceProps) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
        Fuel Endurance
      </h3>
      {!output ? (
        <div className="h-20 flex items-center justify-center text-white/20 text-sm">
          No data
        </div>
      ) : (
        <div>
          <div className="flex items-baseline gap-2 mb-3">
            <span className="text-2xl font-bold font-mono" style={{ color: getConfidenceColor(Math.min(output.mean / 16, 1)) }}>
              {output.mean.toFixed(1)}
            </span>
            <span className="text-xs text-white/40">hours</span>
            <span className="text-xs text-white/30 font-mono ml-auto">
              {'\u00B1'}{output.std.toFixed(2)} hr
            </span>
          </div>

          {/* Range bar: scale to 20 hours max */}
          <div className="relative h-8 bg-white/5 rounded-lg overflow-hidden mb-1">
            {/* P5-P95 range band */}
            <div
              className="absolute h-full rounded-lg"
              style={{
                background: 'linear-gradient(90deg, rgba(239,68,68,0.25), rgba(16,185,129,0.25))',
                left: `${Math.max(0, (output.percentiles.p5 ?? 0) / 20 * 100)}%`,
                width: `${Math.min(100, ((output.percentiles.p95 ?? output.mean) - (output.percentiles.p5 ?? 0)) / 20 * 100)}%`,
              }}
            />
            {/* P25-P75 inner band */}
            <div
              className="absolute h-full bg-gorzen-500/20 rounded-lg"
              style={{
                left: `${Math.max(0, (output.percentiles.p25 ?? output.mean * 0.9) / 20 * 100)}%`,
                width: `${Math.min(100, ((output.percentiles.p75 ?? output.mean * 1.1) - (output.percentiles.p25 ?? output.mean * 0.9)) / 20 * 100)}%`,
              }}
            />
            {/* Median marker */}
            <div
              className="absolute top-0 h-full w-0.5 bg-gorzen-400"
              style={{ left: `${Math.min(100, (output.percentiles.p50 ?? output.mean) / 20 * 100)}%` }}
            />
            {/* Scale ticks */}
            {[0, 4, 8, 12, 16, 20].map((hr) => (
              <div key={hr} className="absolute top-0 h-full w-px bg-white/5" style={{ left: `${hr / 20 * 100}%` }} />
            ))}
          </div>

          <div className="flex justify-between text-[10px] font-mono">
            <span className="text-red-400/60">P5: {(output.percentiles.p5 ?? 0).toFixed(1)}h</span>
            <span className="text-gorzen-400/80">P50: {(output.percentiles.p50 ?? output.mean).toFixed(1)}h</span>
            <span className="text-emerald-400/60">P95: {(output.percentiles.p95 ?? 0).toFixed(1)}h</span>
          </div>

          {flowRate && (
            <div className="mt-3 pt-2 border-t border-white/5 text-[11px] text-white/50 space-y-1">
              <div className="flex justify-between">
                <span>Fuel flow rate</span>
                <span className="font-mono text-white/70">{flowRate.mean.toFixed(0)} g/hr</span>
              </div>
              <div className="flex justify-between">
                <span>Flow rate range</span>
                <span className="font-mono text-white/50">
                  {(flowRate.percentiles.p5 ?? 0).toFixed(0)} - {(flowRate.percentiles.p95 ?? 0).toFixed(0)} g/hr
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
