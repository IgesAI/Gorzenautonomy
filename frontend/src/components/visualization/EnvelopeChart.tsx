import React, { useState } from 'react';
import type { EnvelopeSurface } from '../../types/envelope';
import { chartStyles } from '../../theme/chartStyles';

interface EnvelopeChartProps {
  surface?: EnvelopeSurface | null;
}

function heatColor(feasible: boolean): string {
  if (!feasible) return 'rgba(255,255,255,0.04)';
  return 'rgba(16,185,129,0.55)';
}

export function EnvelopeChart({ surface }: EnvelopeChartProps) {
  const [hover, setHover] = useState<{ x: number; y: number; speed: number; alt: number; feasible: boolean } | null>(null);

  if (!surface) {
    return (
      <div>
        <h3 className={chartStyles.title}>Speed–Altitude Envelope</h3>
        <div className={chartStyles.emptyState}>
          Run "Compute Envelope" to analyze operating limits
        </div>
      </div>
    );
  }

  const { x_values, y_values, z_mean, feasible_mask } = surface;
  const nx = x_values.length;
  const ny = y_values.length;

  const pad = { top: 12, right: 12, bottom: 32, left: 44 };
  const W = 380;
  const H = 240;
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;
  const cellW = plotW / nx;
  const cellH = plotH / ny;

  const feasibleCount = z_mean.flat().filter((v) => v > 0.5).length;
  const totalCount = nx * ny;
  const feasPct = totalCount > 0 ? ((feasibleCount / totalCount) * 100).toFixed(0) : '0';

  const xTicks = [0, Math.floor(nx / 4), Math.floor(nx / 2), Math.floor((3 * nx) / 4), nx - 1].filter((i) => i >= 0 && i < nx);
  const yTicks = [0, Math.floor(ny / 4), Math.floor(ny / 2), Math.floor((3 * ny) / 4), ny - 1].filter((i) => i >= 0 && i < ny);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className={chartStyles.title}>Speed–Altitude Envelope</h3>
        <span className="text-[10px] font-mono text-emerald-400/90 font-medium">
          {feasPct}% feasible
        </span>
      </div>

      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 240 }}>
          {/* Y-axis label */}
          <text
            x={14}
            y={pad.top + plotH / 2}
            textAnchor="middle"
            fontSize="9"
            fill="rgba(255,255,255,0.45)"
            transform={`rotate(-90, 14, ${pad.top + plotH / 2})`}
          >
            Altitude (m)
          </text>

          {/* Y-axis ticks */}
          {yTicks.map((yi) => (
            <g key={`yt-${yi}`}>
              <text
                x={pad.left - 6}
                y={pad.top + (ny - 1 - yi) * cellH + cellH / 2 + 3}
                textAnchor="end"
                fontSize="9"
                fill="rgba(255,255,255,0.4)"
                fontFamily="ui-monospace, monospace"
              >
                {y_values[yi]?.toFixed(0)}
              </text>
              <line
                x1={pad.left}
                y1={pad.top + (ny - 1 - yi) * cellH}
                x2={pad.left + plotW}
                y2={pad.top + (ny - 1 - yi) * cellH}
                stroke="rgba(255,255,255,0.08)"
                strokeWidth="0.5"
              />
            </g>
          ))}

          {/* X-axis ticks */}
          {xTicks.map((xi) => (
            <g key={`xt-${xi}`}>
              <text
                x={pad.left + xi * cellW + cellW / 2}
                y={H - 8}
                textAnchor="middle"
                fontSize="9"
                fill="rgba(255,255,255,0.4)"
                fontFamily="ui-monospace, monospace"
              >
                {x_values[xi]?.toFixed(1)}
              </text>
              <line
                x1={pad.left + xi * cellW}
                y1={pad.top}
                x2={pad.left + xi * cellW}
                y2={pad.top + plotH}
                stroke="rgba(255,255,255,0.08)"
                strokeWidth="0.5"
              />
            </g>
          ))}

          {/* X-axis label */}
          <text x={pad.left + plotW / 2} y={H - 2} textAnchor="middle" fontSize="9" fill="rgba(255,255,255,0.45)">
            Speed (m/s)
          </text>

          {/* Heatmap cells */}
          {y_values.map((_, yi) =>
            x_values.map((_, xi) => {
              const feasible = feasible_mask?.[yi]?.[xi] ?? z_mean[yi][xi] > 0.5;
              return (
                <rect
                  key={`${xi}-${yi}`}
                  x={pad.left + xi * cellW + 0.5}
                  y={pad.top + (ny - 1 - yi) * cellH + 0.5}
                  width={cellW}
                  height={cellH}
                  fill={heatColor(feasible)}
                  rx={1}
                  onMouseEnter={() =>
                    setHover({
                      x: xi,
                      y: yi,
                      speed: x_values[xi] ?? 0,
                      alt: y_values[yi] ?? 0,
                      feasible,
                    })
                  }
                  onMouseLeave={() => setHover(null)}
                />
              );
            })
          )}

          {/* Plot border */}
          <rect
            x={pad.left}
            y={pad.top}
            width={plotW}
            height={plotH}
            fill="none"
            stroke="rgba(255,255,255,0.12)"
            strokeWidth="0.5"
          />
        </svg>

        {hover && (
          <div className="absolute top-2 right-2 bg-black/60 backdrop-blur-sm rounded-lg px-3 py-2 text-[11px] font-mono text-white/90 border border-white/10">
            <div className="font-medium">{hover.feasible ? 'Feasible' : 'Infeasible'}</div>
            <div className="text-white/60 mt-0.5">
              {hover.speed.toFixed(1)} m/s · {hover.alt.toFixed(0)} m
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-4 mt-3 text-[10px] text-white/50">
        <div className="flex items-center gap-2">
          <div className="w-4 h-3 rounded" style={{ background: 'rgba(16,185,129,0.55)' }} />
          <span>Feasible</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-3 rounded bg-white/[0.04]" />
          <span>Infeasible</span>
        </div>
      </div>
    </div>
  );
}
