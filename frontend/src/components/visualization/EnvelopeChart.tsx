import React, { useState } from 'react';
import type { EnvelopeSurface } from '../../types/envelope';

interface EnvelopeChartProps {
  surface?: EnvelopeSurface | null;
}

function heatColor(feasible: boolean, value: number): string {
  if (!feasible) return 'rgba(255,255,255,0.03)';
  const r = Math.round(220 - value * 180);
  const g = Math.round(60 + value * 160);
  const b = Math.round(60);
  return `rgb(${r},${g},${b})`;
}

export function EnvelopeChart({ surface }: EnvelopeChartProps) {
  const [hover, setHover] = useState<{ x: number; y: number; val: string } | null>(null);

  if (!surface) {
    return (
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
          Speed-Altitude Feasibility
        </h3>
        <div className="h-52 flex items-center justify-center text-white/20 text-sm border border-dashed border-white/10 rounded-lg">
          Click "Compute Envelope" to run analysis
        </div>
      </div>
    );
  }

  const { x_values, y_values, z_mean, feasible_mask } = surface;
  const nx = x_values.length;
  const ny = y_values.length;

  const pad = { top: 10, right: 15, bottom: 28, left: 38 };
  const W = 380;
  const H = 220;
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;
  const cellW = plotW / nx;
  const cellH = plotH / ny;

  const feasibleCount = z_mean.flat().filter((v) => v > 0.5).length;
  const totalCount = nx * ny;
  const feasPct = ((feasibleCount / totalCount) * 100).toFixed(0);

  const xTicks = [0, Math.floor(nx / 4), Math.floor(nx / 2), Math.floor(3 * nx / 4), nx - 1];
  const yTicks = [0, Math.floor(ny / 4), Math.floor(ny / 2), Math.floor(3 * ny / 4), ny - 1];

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40">
          Speed-Altitude Envelope
        </h3>
        <span className="text-[10px] font-mono text-gorzen-400">{feasPct}% feasible</span>
      </div>

      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 220 }}>
          {/* Y-axis label */}
          <text x={8} y={pad.top + plotH / 2} textAnchor="middle" fontSize="8" fill="rgba(255,255,255,0.35)" transform={`rotate(-90, 8, ${pad.top + plotH / 2})`}>
            Altitude (m)
          </text>

          {/* Y-axis ticks */}
          {yTicks.map((yi) => (
            <g key={`yt-${yi}`}>
              <text x={pad.left - 3} y={pad.top + (ny - 1 - yi) * cellH + cellH / 2 + 3} textAnchor="end" fontSize="7" fill="rgba(255,255,255,0.3)" fontFamily="monospace">
                {y_values[yi]?.toFixed(0)}
              </text>
              <line x1={pad.left} y1={pad.top + (ny - 1 - yi) * cellH} x2={pad.left + plotW} y2={pad.top + (ny - 1 - yi) * cellH} stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
            </g>
          ))}

          {/* X-axis ticks */}
          {xTicks.map((xi) => (
            <g key={`xt-${xi}`}>
              <text x={pad.left + xi * cellW + cellW / 2} y={H - 6} textAnchor="middle" fontSize="7" fill="rgba(255,255,255,0.3)" fontFamily="monospace">
                {x_values[xi]?.toFixed(0)}
              </text>
              <line x1={pad.left + xi * cellW} y1={pad.top} x2={pad.left + xi * cellW} y2={pad.top + plotH} stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
            </g>
          ))}

          {/* X-axis label */}
          <text x={pad.left + plotW / 2} y={H - 0} textAnchor="middle" fontSize="8" fill="rgba(255,255,255,0.35)">
            Speed (m/s)
          </text>

          {/* Heatmap cells */}
          {y_values.map((_, yi) =>
            x_values.map((_, xi) => {
              const feasible = feasible_mask?.[yi]?.[xi] ?? z_mean[yi][xi] > 0.5;
              return (
                <rect
                  key={`${xi}-${yi}`}
                  x={pad.left + xi * cellW}
                  y={pad.top + (ny - 1 - yi) * cellH}
                  width={cellW + 0.3}
                  height={cellH + 0.3}
                  fill={heatColor(feasible, z_mean[yi][xi])}
                  opacity={feasible ? 0.85 : 0.4}
                  rx={0.5}
                  onMouseEnter={() => setHover({
                    x: xi, y: yi,
                    val: feasible ? `Feasible @ ${x_values[xi]?.toFixed(1)} m/s, ${y_values[yi]?.toFixed(0)} m` : 'Infeasible',
                  })}
                  onMouseLeave={() => setHover(null)}
                />
              );
            }),
          )}

          {/* Plot border */}
          <rect x={pad.left} y={pad.top} width={plotW} height={plotH} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="0.5" />
        </svg>

        {hover && (
          <div className="absolute top-2 right-2 glass-panel px-2 py-1 text-[10px] font-mono text-white/70">
            {hover.val}
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mt-2 text-[10px] text-white/40">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-sm" style={{ background: heatColor(true, 1.0) }} />
          <span>Feasible</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-sm" style={{ background: 'rgba(255,255,255,0.03)' }} />
          <span>Infeasible</span>
        </div>
      </div>
    </div>
  );
}
