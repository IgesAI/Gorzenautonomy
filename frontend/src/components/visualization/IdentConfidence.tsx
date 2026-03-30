import { useState } from 'react';
import type { EnvelopeSurface } from '../../types/envelope';
import { chartStyles } from '../../theme/chartStyles';

interface IdentConfidenceProps {
  surface?: EnvelopeSurface | null;
}

export function IdentConfidence({ surface }: IdentConfidenceProps) {
  const [selectedAlt, setSelectedAlt] = useState<number | null>(null);

  if (!surface) {
    return (
      <div>
        <h3 className={chartStyles.title}>Identification Confidence vs Speed</h3>
        <div className={chartStyles.emptyState}>No data</div>
      </div>
    );
  }

  const { x_values, y_values, z_mean, z_p5, z_p95 } = surface;
  const ny = y_values.length;
  const altIdx = selectedAlt ?? Math.floor(ny / 2);
  const slice = z_mean[altIdx] ?? [];
  const sliceP5 = z_p5[altIdx] ?? [];
  const sliceP95 = z_p95[altIdx] ?? [];
  const altLabel = y_values[altIdx]?.toFixed(0) ?? '?';

  const hasBand = sliceP5.some((v, i) => Math.abs(v - (sliceP95[i] ?? v)) > 0.001);

  const pad = { top: 14, right: 14, bottom: 32, left: 42 };
  const W = 400;
  const H = 180;
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;

  const xScale = slice.length > 1 ? slice.length - 1 : 1;

  const toXY = (arr: number[]) =>
    arr.map((v, i) => ({
      x: pad.left + (i / xScale) * plotW,
      y: pad.top + plotH - Math.max(0, Math.min(1, v)) * plotH,
    }));

  const meanPts = toXY(slice);
  const p5Pts = toXY(sliceP5);
  const p95Pts = toXY(sliceP95);

  const linePath = meanPts.length >= 2
    ? `M${meanPts.map((p) => `${p.x},${p.y}`).join(' L')}`
    : '';

  const bandPath = hasBand && p5Pts.length >= 2
    ? `M${p95Pts.map((p) => `${p.x},${p.y}`).join(' L')} L${[...p5Pts].reverse().map((p) => `${p.x},${p.y}`).join(' L')} Z`
    : '';

  const areaPath = meanPts.length >= 2
    ? `${linePath} L${pad.left + plotW},${pad.top + plotH} L${pad.left},${pad.top + plotH} Z`
    : '';

  const meanVal = slice.length > 0
    ? (slice.reduce((a, b) => a + b, 0) / slice.length * 100).toFixed(1)
    : '—';

  const peakIdx = slice.reduce((best, v, i) => v > (slice[best] ?? 0) ? i : best, 0);
  const peakSpeed = x_values[peakIdx]?.toFixed(1) ?? '—';

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className={chartStyles.title}>Identification Confidence vs Speed</h3>
          <p className="text-[9px] text-white/30 mt-0.5">
            How detection probability changes with airspeed at a fixed altitude
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right mr-2">
            <div className="text-[10px] font-mono text-white/60">Peak at {peakSpeed} m/s</div>
          </div>
          <select
            aria-label="Altitude slice"
            value={altIdx}
            onChange={(e) => setSelectedAlt(parseInt(e.target.value))}
            className="glass-select-sm"
          >
            {y_values.map((alt, i) => (
              <option key={i} value={i}>
                {alt.toFixed(0)} m
              </option>
            ))}
          </select>
        </div>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 200 }}>
        {/* Y-axis label */}
        <text
          x={12} y={pad.top + plotH / 2} textAnchor="middle" fontSize="9"
          fill="rgba(255,255,255,0.4)" fontFamily="ui-monospace, monospace"
          transform={`rotate(-90, 12, ${pad.top + plotH / 2})`}
        >
          P(identification)
        </text>

        {/* Y grid + ticks */}
        {[0, 0.2, 0.4, 0.6, 0.8, 1.0].map((v) => {
          const y = pad.top + plotH - v * plotH;
          return (
            <g key={`g-${v}`}>
              <line
                x1={pad.left} y1={y} x2={pad.left + plotW} y2={y}
                stroke="rgba(255,255,255,0.06)" strokeWidth="0.5"
              />
              <text
                x={pad.left - 5} y={y + 3} textAnchor="end" fontSize="9"
                fill="rgba(255,255,255,0.35)" fontFamily="ui-monospace, monospace"
              >
                {(v * 100).toFixed(0)}%
              </text>
            </g>
          );
        })}

        {/* X ticks */}
        {slice.length > 0 &&
          [0, Math.floor(slice.length / 4), Math.floor(slice.length / 2), Math.floor((3 * slice.length) / 4), slice.length - 1]
            .filter((i, idx, arr) => i >= 0 && i < slice.length && arr.indexOf(i) === idx)
            .map((xi) => (
            <text
              key={`xt-${xi}`}
              x={pad.left + (xi / Math.max(slice.length - 1, 1)) * plotW}
              y={H - 8} textAnchor="middle" fontSize="9"
              fill="rgba(255,255,255,0.35)" fontFamily="ui-monospace, monospace"
            >
              {x_values[xi]?.toFixed(0)}
            </text>
          ))}

        {/* X-axis label */}
        <text x={pad.left + plotW / 2} y={H - 0} textAnchor="middle" fontSize="8"
          fill="rgba(255,255,255,0.3)" fontFamily="ui-monospace, monospace">
          Airspeed (m/s) at {altLabel} m AGL
        </text>

        {/* P5–P95 confidence band */}
        {bandPath && (
          <path d={bandPath} fill="rgba(56, 189, 248, 0.1)" stroke="none" />
        )}

        {/* Mean area fill */}
        {areaPath && (
          <path d={areaPath} fill="url(#confAreaGrad)" />
        )}
        <defs>
          <linearGradient id="confAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(56, 189, 248, 0.2)" />
            <stop offset="100%" stopColor="rgba(56, 189, 248, 0.01)" />
          </linearGradient>
        </defs>

        {/* Mean line */}
        {linePath && (
          <path d={linePath} fill="none" stroke="#38bdf8" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" />
        )}

        {/* 80% threshold */}
        <line
          x1={pad.left} y1={pad.top + plotH * 0.2}
          x2={pad.left + plotW} y2={pad.top + plotH * 0.2}
          stroke="rgba(239,68,68,0.3)" strokeWidth="1" strokeDasharray="4,3"
        />
        <text x={pad.left + plotW + 2} y={pad.top + plotH * 0.2 + 3}
          fontSize="8" fill="rgba(239,68,68,0.5)" fontFamily="ui-monospace, monospace">
          80%
        </text>

        {/* Plot border */}
        <rect x={pad.left} y={pad.top} width={plotW} height={plotH}
          fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="0.5" />
      </svg>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-2 text-[9px] text-white/35">
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-0.5 rounded bg-sky-400" />
          <span>Mean ({meanVal}% avg)</span>
        </div>
        {hasBand && (
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-2.5 rounded-sm bg-sky-400/20" />
            <span>P5–P95 band</span>
          </div>
        )}
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-0 border-t border-dashed border-red-400/50" />
          <span>80% minimum</span>
        </div>
      </div>
    </div>
  );
}
