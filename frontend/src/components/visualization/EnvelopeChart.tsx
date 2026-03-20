import { useState, useRef } from 'react';
import type { EnvelopeSurface } from '../../types/envelope';
import { chartStyles } from '../../theme/chartStyles';
import { colors } from '../../theme/tokens';

interface EnvelopeChartProps {
  surface?: EnvelopeSurface | null;
}

function cellColor(feasible: boolean, identConfidence: number): string {
  if (!feasible) return 'rgba(239,68,68,0.15)';
  if (identConfidence >= 0.9) return 'rgba(16,185,129,0.65)';
  if (identConfidence >= 0.8) return 'rgba(16,185,129,0.45)';
  if (identConfidence >= 0.6) return 'rgba(251,191,36,0.4)';
  return 'rgba(251,191,36,0.25)';
}

function confidenceLabel(feasible: boolean, val: number): { text: string; color: string } {
  if (!feasible) return { text: 'Infeasible', color: '#ef4444' };
  if (val >= 0.9) return { text: 'High Confidence', color: '#10b981' };
  if (val >= 0.8) return { text: 'Feasible', color: '#34d399' };
  if (val >= 0.6) return { text: 'Marginal', color: '#fbbf24' };
  return { text: 'Low Confidence', color: '#f59e0b' };
}

export function EnvelopeChart({ surface }: EnvelopeChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{
    xi: number; yi: number; speed: number; alt: number; feasible: boolean; val: number;
    mouseX: number; mouseY: number;
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

  const xTickStep = Math.max(1, Math.floor(nx / 5));
  const yTickStep = Math.max(1, Math.floor(ny / 5));
  const xTicks = Array.from({ length: Math.ceil(nx / xTickStep) }, (_, i) => Math.min(i * xTickStep, nx - 1));
  if (xTicks[xTicks.length - 1] !== nx - 1) xTicks.push(nx - 1);
  const yTicks = Array.from({ length: Math.ceil(ny / yTickStep) }, (_, i) => Math.min(i * yTickStep, ny - 1));
  if (yTicks[yTicks.length - 1] !== ny - 1) yTicks.push(ny - 1);

  const handleCellHover = (
    e: React.MouseEvent,
    xi: number, yi: number, feasible: boolean, val: number,
  ) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setHover({
      xi, yi,
      speed: x_values[xi] ?? 0,
      alt: y_values[yi] ?? 0,
      feasible, val,
      mouseX: e.clientX - rect.left,
      mouseY: e.clientY - rect.top,
    });
  };

  const label = hover ? confidenceLabel(hover.feasible, hover.val) : null;

  // Position tooltip so it doesn't overflow the container
  const tipW = 180;
  const tipH = 90;
  let tipX = (hover?.mouseX ?? 0) + 12;
  let tipY = (hover?.mouseY ?? 0) - tipH - 8;
  const containerW = containerRef.current?.clientWidth ?? W;
  if (tipX + tipW > containerW) tipX = (hover?.mouseX ?? 0) - tipW - 12;
  if (tipY < 0) tipY = (hover?.mouseY ?? 0) + 16;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className={chartStyles.title}>Speed-Altitude Envelope</h3>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono font-medium" style={{ color: colors.status.success }}>
            {feasPct}% feasible
          </span>
          <span className="text-[10px] font-mono text-white/35">
            {nx}&times;{ny}
          </span>
        </div>
      </div>

      <div className="relative" ref={containerRef}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ maxHeight: 260 }}
          onMouseLeave={() => setHover(null)}
        >
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

          {/* Heatmap cells — no gaps, seamless grid */}
          {y_values.map((_, yi) =>
            x_values.map((_, xi) => {
              const feasible = feasible_mask?.[yi]?.[xi] ?? z_mean[yi][xi] > 0.5;
              const val = z_mean[yi][xi];
              return (
                <rect
                  key={`${xi}-${yi}`}
                  x={pad.left + xi * cellW}
                  y={pad.top + (ny - 1 - yi) * cellH}
                  width={cellW + 0.5}
                  height={cellH + 0.5}
                  fill={cellColor(!!feasible, val)}
                  onMouseMove={(e) => handleCellHover(e, xi, yi, !!feasible, val)}
                />
              );
            })
          )}

          {/* Hover crosshair */}
          {hover && (
            <>
              {/* Horizontal line */}
              <line
                x1={pad.left}
                y1={pad.top + (ny - 1 - hover.yi) * cellH + cellH / 2}
                x2={pad.left + plotW}
                y2={pad.top + (ny - 1 - hover.yi) * cellH + cellH / 2}
                stroke="rgba(255,255,255,0.25)" strokeWidth="0.5" strokeDasharray="3,3"
                pointerEvents="none"
              />
              {/* Vertical line */}
              <line
                x1={pad.left + hover.xi * cellW + cellW / 2}
                y1={pad.top}
                x2={pad.left + hover.xi * cellW + cellW / 2}
                y2={pad.top + plotH}
                stroke="rgba(255,255,255,0.25)" strokeWidth="0.5" strokeDasharray="3,3"
                pointerEvents="none"
              />
              {/* Cell highlight */}
              <rect
                x={pad.left + hover.xi * cellW}
                y={pad.top + (ny - 1 - hover.yi) * cellH}
                width={cellW}
                height={cellH}
                fill="none"
                stroke="rgba(255,255,255,0.8)"
                strokeWidth="1.5"
                pointerEvents="none"
              />
            </>
          )}

          {/* Plot border */}
          <rect x={pad.left} y={pad.top} width={plotW} height={plotH}
            fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="0.5" />
        </svg>

        {/* Tooltip — follows cursor */}
        {hover && label && (
          <div
            className="absolute pointer-events-none z-10"
            style={{ left: tipX, top: tipY, width: tipW }}
          >
            <div className="bg-black/80 backdrop-blur-xl rounded-lg px-3 py-2.5 border border-white/10 shadow-xl">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: label.color }} />
                <span className="text-[11px] font-semibold" style={{ color: label.color }}>{label.text}</span>
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px] font-mono">
                <span className="text-white/40">Speed</span>
                <span className="text-white/85 text-right">{hover.speed.toFixed(1)} m/s</span>
                <span className="text-white/40">Altitude</span>
                <span className="text-white/85 text-right">{hover.alt.toFixed(0)} m</span>
                <span className="text-white/40">Confidence</span>
                <span className="text-right" style={{ color: label.color }}>{(hover.val * 100).toFixed(1)}%</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3">
        {[
          { bg: 'rgba(16,185,129,0.65)', label: 'High (>90%)' },
          { bg: 'rgba(16,185,129,0.45)', label: 'Good (>80%)' },
          { bg: 'rgba(251,191,36,0.4)', label: 'Marginal (>60%)' },
          { bg: 'rgba(251,191,36,0.25)', label: 'Low (<60%)' },
          { bg: 'rgba(239,68,68,0.15)', label: 'Infeasible' },
        ].map(({ bg, label: l }) => (
          <div key={l} className="flex items-center gap-1.5 text-[9px] text-white/45">
            <div className="w-3 h-2.5 rounded-sm" style={{ background: bg }} />
            <span>{l}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
