import React from 'react';
import type { EnvelopeSurface } from '../../types/envelope';
import { getConfidenceColor } from '../../theme/tokens';

interface EnvelopeChartProps {
  surface?: EnvelopeSurface | null;
}

export function EnvelopeChart({ surface }: EnvelopeChartProps) {
  if (!surface) {
    return (
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
          Speed-Altitude Feasibility
        </h3>
        <div className="h-48 flex items-center justify-center text-white/20 text-sm">
          Run envelope computation to see results
        </div>
      </div>
    );
  }

  const { x_values, y_values, z_mean, feasible_mask } = surface;
  const nx = x_values.length;
  const ny = y_values.length;
  const cellW = 100 / nx;
  const cellH = 100 / ny;

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
        Speed-Altitude Feasibility
      </h3>
      <div className="relative" style={{ paddingBottom: '75%' }}>
        <svg
          viewBox="0 0 100 75"
          className="absolute inset-0 w-full h-full"
          preserveAspectRatio="none"
        >
          {y_values.map((_, yi) =>
            x_values.map((_, xi) => {
              const feasible = feasible_mask?.[yi]?.[xi] ?? z_mean[yi][xi] > 0.5;
              const val = z_mean[yi][xi];
              return (
                <rect
                  key={`${xi}-${yi}`}
                  x={xi * cellW}
                  y={(ny - 1 - yi) * cellH}
                  width={cellW + 0.5}
                  height={cellH + 0.5}
                  fill={feasible ? getConfidenceColor(val) : 'rgba(255,255,255,0.03)'}
                  opacity={feasible ? 0.6 : 0.3}
                />
              );
            }),
          )}
        </svg>
      </div>
      <div className="flex justify-between mt-2 text-[10px] text-white/30 font-mono">
        <span>{x_values[0]} m/s</span>
        <span>{surface.x_label}</span>
        <span>{x_values[nx - 1]} m/s</span>
      </div>
    </div>
  );
}
