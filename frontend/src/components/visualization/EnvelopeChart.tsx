import React, { useState } from 'react';
import type { EnvelopeSurface } from '../../types/envelope';
import { chartStyles } from '../../theme/chartStyles';
import { colors } from '../../theme/tokens';

interface EnvelopeChartProps {
  surface?: EnvelopeSurface | null;
}

function cellColor(feasible: boolean, identConfidence: number): string {
  if (!feasible) return 'rgba(239,68,68,0.15)';
  // Green gradient based on identification confidence
  if (identConfidence >= 0.9) return 'rgba(16,185,129,0.65)';
  if (identConfidence >= 0.8) return 'rgba(16,185,129,0.45)';
  if (identConfidence >= 0.6) return 'rgba(251,191,36,0.4)';
  return 'rgba(251,191,36,0.25)';
}

export function EnvelopeChart({ surface }: EnvelopeChartProps) {
  const [hover, setHover] = useState<{
    x: number; y: number; speed: number; alt: number; feasible: boolean; val: number;
  } | null>(null);

  if (!surface) {
    return (
      <div>
        <h3 className={chartStyles.title}>Speed-Altitude Envelope</h3>
        <div className={chartStyles.emptyState}>
          Run "Compute Envelope" to analyze operating limits
        </div>
      </div>
    );
  }

  const { x_values, y_values, z_mean, feasible_mask } = surface;
  const nx = x_values.length;
  const ny = y_values.length;

  const pad = { top: 14, right: 16, bottom: 36, left: 50 };
  const W = 400;
  const H = 260;
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;
  const cellW = plotW / nx;
  const cellH = plotH / ny;

  const feasibleCount = (feasible_mask ?? z_mean).flat().filter((v) =>
    typeof v === 'boolean' ? v : v > 0.5
  ).length;
  const totalCount = nx * ny;
  const feasPct = totalCount > 0 ? ((feasibleCount / totalCount) * 100).toFixed(0) : '0';

  // Generate ~5 evenly spaced ticks for each axis
  const xTickStep = Math.max(1, Math.floor(nx / 5));
  const yTickStep = Math.max(1, Math.floor(ny / 5));
  const xTicks = Array.from({ length: Math.ceil(nx / xTickStep) }, (_, i) => Math.min(i * xTickStep, nx - 1));
  if (xTicks[xTicks.length - 1] !== nx - 1) xTicks.push(nx - 1);
  const yTicks = Array.from({ length: Math.ceil(ny / yTickStep) }, (_, i) => Math.min(i * yTickStep, ny - 1));
  if (yTicks[yTicks.length - 1] !== ny - 1) yTicks.push(ny - 1);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className={chartStyles.title}>Speed-Altitude Envelope</h3>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono font-medium" style={{ color: colors.status.success }}>
            {feasPct}% feasible
          </span>
          <span className="text-[10px] font-mono text-white/35">
            {nx}x{ny} grid
          </span>
        </div>
      </div>

      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 260 }}>
          {/* Y-axis label */}
          <text
            x={12} y={pad.top + plotH / 2} textAnchor="middle" fontSize="9"
            fill="rgba(255,255,255,0.5)" fontFamily="ui-monospace, monospace"
            transform={`rotate(-90, 12, ${pad.top + plotH / 2})`}
          >
            Altitude (m)
          </text>

          {/* Grid lines and Y-axis ticks */}
          {yTicks.map((yi) => {
            const y = pad.top + (ny - 1 - yi) * cellH + cellH / 2;
            return (
              <g key={`yt-${yi}`}>
                <line x1={pad.left} y1={y} x2={pad.left + plotW} y2={y}
                  stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
                <text x={pad.left - 6} y={y + 3} textAnchor="end" fontSize="9"
                  fill="rgba(255,255,255,0.45)" fontFamily="ui-monospace, monospace">
                  {y_values[yi]?.toFixed(0)}
                </text>
              </g>
            );
          })}

          {/* X-axis ticks */}
          {xTicks.map((xi) => {
            const x = pad.left + xi * cellW + cellW / 2;
            return (
              <g key={`xt-${xi}`}>
                <line x1={x} y1={pad.top} x2={x} y2={pad.top + plotH}
                  stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
                <text x={x} y={H - 10} textAnchor="middle" fontSize="9"
                  fill="rgba(255,255,255,0.45)" fontFamily="ui-monospace, monospace">
                  {x_values[xi]?.toFixed(0)}
                </text>
              </g>
            );
          })}

          {/* X-axis label */}
          <text x={pad.left + plotW / 2} y={H - 1} textAnchor="middle" fontSize="9"
            fill="rgba(255,255,255,0.5)" fontFamily="ui-monospace, monospace">
            Speed (m/s)
          </text>

          {/* Heatmap cells */}
          {y_values.map((_, yi) =>
            x_values.map((_, xi) => {
              const feasible = feasible_mask?.[yi]?.[xi] ?? z_mean[yi][xi] > 0.5;
              const val = z_mean[yi][xi];
              return (
                <rect
                  key={`${xi}-${yi}`}
                  x={pad.left + xi * cellW + 0.5}
                  y={pad.top + (ny - 1 - yi) * cellH + 0.5}
                  width={cellW - 0.5}
                  height={cellH - 0.5}
                  fill={cellColor(!!feasible, val)}
                  rx={1.5}
                  className="transition-opacity duration-100"
                  opacity={hover && (hover.x !== xi || hover.y !== yi) ? 0.7 : 1}
                  onMouseEnter={() => setHover({ x: xi, y: yi, speed: x_values[xi] ?? 0, alt: y_values[yi] ?? 0, feasible: !!feasible, val })}
                  onMouseLeave={() => setHover(null)}
                />
              );
            })
          )}

          {/* Hover highlight */}
          {hover && (
            <rect
              x={pad.left + hover.x * cellW}
              y={pad.top + (ny - 1 - hover.y) * cellH}
              width={cellW}
              height={cellH}
              fill="none"
              stroke="rgba(255,255,255,0.7)"
              strokeWidth="1.5"
              rx={2}
              pointerEvents="none"
            />
          )}

          {/* Plot border */}
          <rect x={pad.left} y={pad.top} width={plotW} height={plotH}
            fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="0.5" />
        </svg>

        {/* Tooltip */}
        {hover && (
          <div className="absolute top-3 right-3 bg-black/70 backdrop-blur-md rounded-xl px-3.5 py-2.5 border border-white/10 shadow-lg">
            <div className="flex items-center gap-2 mb-1.5">
              <div className={`w-2.5 h-2.5 rounded-full ${hover.feasible ? 'bg-emerald-400' : 'bg-red-400'}`} />
              <span className="text-xs font-semibold text-white/90">{hover.feasible ? 'Feasible' : 'Infeasible'}</span>
            </div>
            <div className="space-y-0.5 text-[11px] font-mono">
              <div className="text-white/60">Speed: <span className="text-white/90">{hover.speed.toFixed(1)} m/s</span></div>
              <div className="text-white/60">Altitude: <span className="text-white/90">{hover.alt.toFixed(0)} m</span></div>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-5 mt-3">
        <div className="flex items-center gap-4 text-[10px] text-white/50">
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-3 rounded" style={{ background: 'rgba(16,185,129,0.65)' }} />
            <span>High confidence</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-3 rounded" style={{ background: 'rgba(16,185,129,0.35)' }} />
            <span>Feasible</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-3 rounded" style={{ background: 'rgba(251,191,36,0.35)' }} />
            <span>Marginal</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-3 rounded" style={{ background: 'rgba(239,68,68,0.15)' }} />
            <span>Infeasible</span>
          </div>
        </div>
      </div>
    </div>
  );
}
