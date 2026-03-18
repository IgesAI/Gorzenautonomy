import React from 'react';
import type { EnvelopeSurface } from '../../types/envelope';
import { getConfidenceColor } from '../../theme/tokens';

interface IdentConfidenceProps {
  surface?: EnvelopeSurface | null;
}

export function IdentConfidence({ surface }: IdentConfidenceProps) {
  if (!surface) {
    return (
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
          Identification Confidence
        </h3>
        <div className="h-32 flex items-center justify-center text-white/20 text-sm">
          No data
        </div>
      </div>
    );
  }

  const { x_values, z_mean } = surface;
  const midRow = Math.floor(z_mean.length / 2);
  const confidenceSlice = z_mean[midRow] ?? [];

  const maxVal = Math.max(...confidenceSlice, 0.01);
  const barH = 80;

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
        Identification Confidence vs Speed
      </h3>
      <div className="relative h-24">
        <svg viewBox={`0 0 ${x_values.length * 6} ${barH}`} className="w-full h-full" preserveAspectRatio="none">
          {confidenceSlice.map((val, i) => {
            const h = (val / maxVal) * barH;
            return (
              <rect
                key={i}
                x={i * 6}
                y={barH - h}
                width={5}
                height={h}
                fill={getConfidenceColor(val)}
                opacity={0.7}
                rx={1}
              />
            );
          })}
        </svg>
      </div>
      <div className="flex justify-between mt-1 text-[10px] text-white/30 font-mono">
        <span>{x_values[0]?.toFixed(0)} m/s</span>
        <span>Speed</span>
        <span>{x_values[x_values.length - 1]?.toFixed(0)} m/s</span>
      </div>
    </div>
  );
}
