import { useState, useRef, useMemo } from 'react';
import type { EnvelopeSurface } from '../../types/envelope';
import { chartStyles } from '../../theme/chartStyles';

interface EnvelopeChartProps {
  surface?: EnvelopeSurface | null;
  identSurface?: EnvelopeSurface | null;
}

function interpolateColor(t: number): string {
  // Colorblind-safe sequential: deep navy → teal → amber → white
  // Based on Viridis-inspired stops tuned for dark backgrounds
  const stops = [
    { t: 0.0, r: 30,  g: 30,  b: 60  },
    { t: 0.3, r: 30,  g: 100, b: 140 },
    { t: 0.5, r: 40,  g: 170, b: 160 },
    { t: 0.7, r: 160, g: 210, b: 90  },
    { t: 1.0, r: 255, g: 230, b: 80  },
  ];

  const clamped = Math.max(0, Math.min(1, t));
  let lo = stops[0], hi = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (clamped >= stops[i].t && clamped <= stops[i + 1].t) {
      lo = stops[i];
      hi = stops[i + 1];
      break;
    }
  }
  const f = hi.t === lo.t ? 0 : (clamped - lo.t) / (hi.t - lo.t);
  const r = Math.round(lo.r + f * (hi.r - lo.r));
  const g = Math.round(lo.g + f * (hi.g - lo.g));
  const b = Math.round(lo.b + f * (hi.b - lo.b));
  return `rgb(${r},${g},${b})`;
}

function cellColor(feasible: boolean, confidence: number): string {
  if (!feasible) return 'rgba(80, 30, 30, 0.5)';
  return interpolateColor(confidence);
}

function confidenceLabel(feasible: boolean, val: number): { text: string; color: string } {
  if (!feasible) return { text: 'Infeasible', color: '#ef4444' };
  if (val >= 0.9) return { text: 'Excellent', color: '#fde047' };
  if (val >= 0.8) return { text: 'Good', color: '#86efac' };
  if (val >= 0.6) return { text: 'Marginal', color: '#38bdf8' };
  return { text: 'Low', color: '#7dd3fc' };
}

export function EnvelopeChart({ surface, identSurface }: EnvelopeChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{
    xi: number; yi: number; speed: number; alt: number;
    feasible: boolean; confidence: number;
    mouseX: number; mouseY: number;
  } | null>(null);

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
  const identZ = identSurface?.z_mean;
  const nx = x_values.length;
  const ny = y_values.length;

  const pad = { top: 14, right: 16, bottom: 36, left: 50 };
  const W = 440;
  const H = 280;
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;
  const cellW = plotW / nx;
  const cellH = plotH / ny;

  const stats = useMemo(() => {
    let feasibleCount = 0;
    let highConfCount = 0;
    const total = nx * ny;
    for (let yi = 0; yi < ny; yi++) {
      for (let xi = 0; xi < nx; xi++) {
        const f = feasible_mask?.[yi]?.[xi] ?? z_mean[yi][xi] > 0.5;
        if (f) {
          feasibleCount++;
          const conf = identZ?.[yi]?.[xi] ?? z_mean[yi][xi];
          if (conf >= 0.8) highConfCount++;
        }
      }
    }
    return {
      feasPct: total > 0 ? ((feasibleCount / total) * 100).toFixed(0) : '0',
      highPct: total > 0 ? ((highConfCount / total) * 100).toFixed(0) : '0',
      total,
      feasibleCount,
    };
  }, [nx, ny, feasible_mask, z_mean, identZ]);

  const xTickStep = Math.max(1, Math.floor(nx / 6));
  const yTickStep = Math.max(1, Math.floor(ny / 6));
  const xTicks = Array.from({ length: Math.ceil(nx / xTickStep) }, (_, i) => Math.min(i * xTickStep, nx - 1));
  if (xTicks[xTicks.length - 1] !== nx - 1) xTicks.push(nx - 1);
  const yTicks = Array.from({ length: Math.ceil(ny / yTickStep) }, (_, i) => Math.min(i * yTickStep, ny - 1));
  if (yTicks[yTicks.length - 1] !== ny - 1) yTicks.push(ny - 1);

  const handleCellHover = (
    e: React.MouseEvent,
    xi: number, yi: number, feasible: boolean, confidence: number,
  ) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setHover({
      xi, yi,
      speed: x_values[xi] ?? 0,
      alt: y_values[yi] ?? 0,
      feasible, confidence,
      mouseX: e.clientX - rect.left,
      mouseY: e.clientY - rect.top,
    });
  };

  const label = hover ? confidenceLabel(hover.feasible, hover.confidence) : null;

  const tipW = 200;
  const tipH = 100;
  let tipX = (hover?.mouseX ?? 0) + 12;
  let tipY = (hover?.mouseY ?? 0) - tipH - 8;
  const containerW = containerRef.current?.clientWidth ?? W;
  if (tipX + tipW > containerW) tipX = (hover?.mouseX ?? 0) - tipW - 12;
  if (tipY < 0) tipY = (hover?.mouseY ?? 0) + 16;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className={chartStyles.title}>Speed–Altitude Envelope</h3>
          <p className="text-[9px] text-white/30 mt-0.5">
            Color = identification confidence within feasible region
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-[11px] font-mono font-semibold text-emerald-400">{stats.feasPct}%</div>
            <div className="text-[8px] text-white/30 uppercase tracking-wider">Feasible</div>
          </div>
          <div className="text-right">
            <div className="text-[11px] font-mono font-semibold text-amber-300">{stats.highPct}%</div>
            <div className="text-[8px] text-white/30 uppercase tracking-wider">High Conf</div>
          </div>
          <span className="text-[10px] font-mono text-white/25">
            {nx}&times;{ny}
          </span>
        </div>
      </div>

      <div className="relative" ref={containerRef}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ maxHeight: 300 }}
          onMouseLeave={() => setHover(null)}
          role="img"
          aria-label={`Speed-altitude heatmap showing ${stats.feasPct}% of grid is feasible`}
        >
          {/* Y-axis label */}
          <text
            x={12} y={pad.top + plotH / 2} textAnchor="middle" fontSize="9"
            fill="rgba(255,255,255,0.45)" fontFamily="ui-monospace, monospace"
            transform={`rotate(-90, 12, ${pad.top + plotH / 2})`}
          >
            Altitude (m AGL)
          </text>

          {/* Grid lines and Y-axis ticks */}
          {yTicks.map((yi) => {
            const y = pad.top + (ny - 1 - yi) * cellH + cellH / 2;
            return (
              <g key={`yt-${yi}`}>
                <line x1={pad.left} y1={y} x2={pad.left + plotW} y2={y}
                  stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" />
                <text x={pad.left - 6} y={y + 3} textAnchor="end" fontSize="9"
                  fill="rgba(255,255,255,0.4)" fontFamily="ui-monospace, monospace">
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
                  stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" />
                <text x={x} y={H - 10} textAnchor="middle" fontSize="9"
                  fill="rgba(255,255,255,0.4)" fontFamily="ui-monospace, monospace">
                  {x_values[xi]?.toFixed(0)}
                </text>
              </g>
            );
          })}

          <text x={pad.left + plotW / 2} y={H - 1} textAnchor="middle" fontSize="9"
            fill="rgba(255,255,255,0.45)" fontFamily="ui-monospace, monospace">
            Airspeed (m/s)
          </text>

          {/* Heatmap cells — uses ident confidence for color within feasible cells */}
          {y_values.map((_, yi) =>
            x_values.map((_, xi) => {
              const feasible = feasible_mask?.[yi]?.[xi] ?? z_mean[yi][xi] > 0.5;
              const confidence = identZ?.[yi]?.[xi] ?? (feasible ? 0.5 : 0);
              return (
                <rect
                  key={`${xi}-${yi}`}
                  x={pad.left + xi * cellW}
                  y={pad.top + (ny - 1 - yi) * cellH}
                  width={cellW + 0.5}
                  height={cellH + 0.5}
                  fill={cellColor(!!feasible, confidence)}
                  onMouseMove={(e) => handleCellHover(e, xi, yi, !!feasible, confidence)}
                  className="transition-opacity duration-75"
                />
              );
            })
          )}

          {/* Hover crosshair */}
          {hover && (
            <>
              <line
                x1={pad.left}
                y1={pad.top + (ny - 1 - hover.yi) * cellH + cellH / 2}
                x2={pad.left + plotW}
                y2={pad.top + (ny - 1 - hover.yi) * cellH + cellH / 2}
                stroke="rgba(255,255,255,0.3)" strokeWidth="0.5" strokeDasharray="3,3"
                pointerEvents="none"
              />
              <line
                x1={pad.left + hover.xi * cellW + cellW / 2}
                y1={pad.top}
                x2={pad.left + hover.xi * cellW + cellW / 2}
                y2={pad.top + plotH}
                stroke="rgba(255,255,255,0.3)" strokeWidth="0.5" strokeDasharray="3,3"
                pointerEvents="none"
              />
              <rect
                x={pad.left + hover.xi * cellW}
                y={pad.top + (ny - 1 - hover.yi) * cellH}
                width={cellW}
                height={cellH}
                fill="none"
                stroke="rgba(255,255,255,0.9)"
                strokeWidth="1.5"
                pointerEvents="none"
              />
            </>
          )}

          <rect x={pad.left} y={pad.top} width={plotW} height={plotH}
            fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="0.5" />
        </svg>

        {/* Tooltip */}
        {hover && label && (
          <div
            className="absolute pointer-events-none z-10"
            style={{ left: tipX, top: tipY, width: tipW }}
          >
            <div className="bg-black/90 backdrop-blur-xl rounded-lg px-3 py-2.5 border border-white/10 shadow-2xl">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: label.color }} />
                <span className="text-[11px] font-semibold" style={{ color: label.color }}>{label.text}</span>
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[10px] font-mono">
                <span className="text-white/40">Airspeed</span>
                <span className="text-white/85 text-right">{hover.speed.toFixed(1)} m/s</span>
                <span className="text-white/40">Altitude</span>
                <span className="text-white/85 text-right">{hover.alt.toFixed(0)} m AGL</span>
                <span className="text-white/40">Confidence</span>
                <span className="text-right" style={{ color: label.color }}>
                  {hover.feasible ? `${(hover.confidence * 100).toFixed(1)}%` : '—'}
                </span>
                <span className="text-white/40">Feasible</span>
                <span className={`text-right ${hover.feasible ? 'text-emerald-400' : 'text-red-400'}`}>
                  {hover.feasible ? 'Yes' : 'No'}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Color scale legend */}
      <div className="flex items-center gap-3 mt-3">
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-3 rounded-sm" style={{ background: 'rgba(80, 30, 30, 0.5)' }} />
          <span className="text-[9px] text-white/40">Infeasible</span>
        </div>
        <div className="flex-1 h-3 rounded-sm overflow-hidden flex">
          {Array.from({ length: 20 }).map((_, i) => (
            <div
              key={i}
              className="flex-1 h-full"
              style={{ background: interpolateColor(i / 19) }}
            />
          ))}
        </div>
        <div className="flex items-center gap-3 text-[9px] text-white/40">
          <span>0%</span>
          <span>50%</span>
          <span>100%</span>
        </div>
      </div>
      <div className="text-[8px] text-white/25 text-center mt-1">Identification Confidence</div>
    </div>
  );
}
