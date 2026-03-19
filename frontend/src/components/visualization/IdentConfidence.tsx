import React, { useState } from 'react';
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
        <h3 className={chartStyles.title}>Identification Confidence</h3>
        <div className={chartStyles.emptyState}>No data</div>
      </div>
    );
  }

  const { x_values, y_values, z_mean } = surface;
  const ny = y_values.length;
  const altIdx = selectedAlt ?? Math.floor(ny / 2);
  const slice = z_mean[altIdx] ?? [];
  const altLabel = y_values[altIdx]?.toFixed(0) ?? '?';

  const pad = { top: 12, right: 14, bottom: 28, left: 38 };
  const W = 380;
  const H = 160;
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;

  const maxVal = 1.0;
  const xScale = slice.length > 1 ? slice.length - 1 : 1;
  const points = slice.map((v, i) => {
    const x = pad.left + (i / xScale) * plotW;
    const y = pad.top + plotH - (v / maxVal) * plotH;
    return `${x},${y}`;
  });
  const linePath = points.length >= 2 ? `M${points.join(' L')}` : points.length === 1 ? `M${points[0]} L${points[0]}` : '';
  const areaPath =
    linePath && points.length > 1
      ? `${linePath} L${pad.left + plotW},${pad.top + plotH} L${pad.left},${pad.top + plotH} Z`
      : '';

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className={chartStyles.title}>Identification Confidence</h3>
        <select
          aria-label="Altitude slice"
          value={altIdx}
          onChange={(e) => setSelectedAlt(parseInt(e.target.value))}
          className="text-[10px] bg-white/5 border border-white/10 rounded-md px-2 py-1 text-white/80 font-mono focus:outline-none focus:ring-1 focus:ring-white/20"
        >
          {y_values.map((alt, i) => (
            <option key={i} value={i}>
              {alt.toFixed(0)} m
            </option>
          ))}
        </select>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 160 }}>
        {/* Y-axis label */}
        <text
          x={12}
          y={pad.top + plotH / 2}
          textAnchor="middle"
          fontSize="9"
          fill="rgba(255,255,255,0.45)"
          transform={`rotate(-90, 12, ${pad.top + plotH / 2})`}
        >
          Confidence
        </text>

        {/* Grid & Y ticks */}
        {[0, 0.25, 0.5, 0.75, 1.0].map((v) => {
          const y = pad.top + plotH - (v / maxVal) * plotH;
          return (
            <g key={`g-${v}`}>
              <line
                x1={pad.left}
                y1={y}
                x2={pad.left + plotW}
                y2={y}
                stroke="rgba(255,255,255,0.08)"
                strokeWidth="0.5"
              />
              <text
                x={pad.left - 6}
                y={y + 3}
                textAnchor="end"
                fontSize="9"
                fill="rgba(255,255,255,0.4)"
                fontFamily="ui-monospace, monospace"
              >
                {(v * 100).toFixed(0)}%
              </text>
            </g>
          );
        })}

        {/* X ticks */}
        {slice.length > 0 &&
          [0, Math.floor(slice.length / 4), Math.floor(slice.length / 2), Math.floor((3 * slice.length) / 4), slice.length - 1]
            .filter((i) => i >= 0 && i < slice.length)
            .map((xi) => (
            <text
              key={`xt-${xi}`}
              x={pad.left + (xi / Math.max(slice.length - 1, 1)) * plotW}
              y={H - 6}
              textAnchor="middle"
              fontSize="9"
              fill="rgba(255,255,255,0.4)"
              fontFamily="ui-monospace, monospace"
            >
              {x_values[xi]?.toFixed(1)}
            </text>
          ))}

        {/* Area fill */}
        {areaPath && (
          <>
            <path d={areaPath} fill="url(#confGrad)" />
            <defs>
              <linearGradient id="confGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="rgba(47,127,255,0.25)" />
                <stop offset="100%" stopColor="rgba(47,127,255,0.02)" />
              </linearGradient>
            </defs>
          </>
        )}

        {/* Line */}
        {linePath && <path d={linePath} fill="none" stroke="#2f7fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />}

        {/* 80% threshold */}
        <line
          x1={pad.left}
          y1={pad.top + plotH * 0.2}
          x2={pad.left + plotW}
          y2={pad.top + plotH * 0.2}
          stroke="rgba(239,68,68,0.35)"
          strokeWidth="1"
          strokeDasharray="4,3"
        />
        <text x={pad.left + plotW + 4} y={pad.top + plotH * 0.2 + 3} fontSize="8" fill="rgba(239,68,68,0.6)">
          80% min
        </text>

        {/* Plot border */}
        <rect
          x={pad.left}
          y={pad.top}
          width={plotW}
          height={plotH}
          fill="none"
          stroke="rgba(255,255,255,0.1)"
          strokeWidth="0.5"
        />
      </svg>

      <div className="text-[10px] text-white/40 text-center mt-2 font-mono">
        Altitude: {altLabel} m · Speed (m/s)
      </div>
    </div>
  );
}
