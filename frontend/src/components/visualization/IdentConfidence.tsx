import React, { useState } from 'react';
import type { EnvelopeSurface } from '../../types/envelope';
import { getConfidenceColor } from '../../theme/tokens';

interface IdentConfidenceProps {
  surface?: EnvelopeSurface | null;
}

export function IdentConfidence({ surface }: IdentConfidenceProps) {
  const [selectedAlt, setSelectedAlt] = useState<number | null>(null);

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

  const { x_values, y_values, z_mean } = surface;
  const ny = y_values.length;
  const altIdx = selectedAlt ?? Math.floor(ny / 2);
  const slice = z_mean[altIdx] ?? [];
  const altLabel = y_values[altIdx]?.toFixed(0) ?? '?';

  const pad = { top: 8, right: 10, bottom: 24, left: 32 };
  const W = 380;
  const H = 140;
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;

  const maxVal = 1.0;
  const points = slice.map((v, i) => {
    const x = pad.left + (i / (slice.length - 1)) * plotW;
    const y = pad.top + plotH - (v / maxVal) * plotH;
    return `${x},${y}`;
  });
  const linePath = `M${points.join(' L')}`;
  const areaPath = `${linePath} L${pad.left + plotW},${pad.top + plotH} L${pad.left},${pad.top + plotH} Z`;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40">
          ID Confidence vs Speed
        </h3>
        <select
          aria-label="Select altitude"
          value={altIdx}
          onChange={(e) => setSelectedAlt(parseInt(e.target.value))}
          className="text-[10px] bg-white/5 border border-white/10 rounded px-1.5 py-0.5 text-white/60 font-mono"
        >
          {y_values.map((alt, i) => (
            <option key={i} value={i}>{alt.toFixed(0)}m</option>
          ))}
        </select>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 140 }}>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1.0].map((v) => {
          const y = pad.top + plotH - (v / maxVal) * plotH;
          return (
            <g key={`g-${v}`}>
              <line x1={pad.left} y1={y} x2={pad.left + plotW} y2={y} stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
              <text x={pad.left - 3} y={y + 3} textAnchor="end" fontSize="7" fill="rgba(255,255,255,0.3)" fontFamily="monospace">
                {(v * 100).toFixed(0)}%
              </text>
            </g>
          );
        })}

        {/* X ticks */}
        {[0, Math.floor(slice.length / 4), Math.floor(slice.length / 2), Math.floor(3 * slice.length / 4), slice.length - 1].map((xi) => (
          <text key={`xt-${xi}`} x={pad.left + (xi / (slice.length - 1)) * plotW} y={H - 4} textAnchor="middle" fontSize="7" fill="rgba(255,255,255,0.3)" fontFamily="monospace">
            {x_values[xi]?.toFixed(0)}
          </text>
        ))}

        {/* Area fill */}
        <path d={areaPath} fill="url(#confGrad)" />
        <defs>
          <linearGradient id="confGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(47,127,255,0.3)" />
            <stop offset="100%" stopColor="rgba(47,127,255,0.02)" />
          </linearGradient>
        </defs>

        {/* Line */}
        <path d={linePath} fill="none" stroke="#2f7fff" strokeWidth="1.5" />

        {/* Threshold line at 80% */}
        <line
          x1={pad.left} y1={pad.top + plotH * 0.2}
          x2={pad.left + plotW} y2={pad.top + plotH * 0.2}
          stroke="rgba(239,68,68,0.4)" strokeWidth="0.8" strokeDasharray="4,3"
        />
        <text x={pad.left + plotW + 2} y={pad.top + plotH * 0.2 + 3} fontSize="6" fill="rgba(239,68,68,0.5)">
          80%
        </text>

        {/* Data points */}
        {slice.map((v, i) => {
          const x = pad.left + (i / (slice.length - 1)) * plotW;
          const y = pad.top + plotH - (v / maxVal) * plotH;
          return (
            <circle key={i} cx={x} cy={y} r={1.5} fill={getConfidenceColor(v)} opacity={0.8} />
          );
        })}

        <text x={pad.left + plotW / 2} y={H} textAnchor="middle" fontSize="7" fill="rgba(255,255,255,0.3)">
          Speed (m/s)
        </text>
      </svg>

      <div className="text-[10px] text-white/30 text-center mt-1 font-mono">
        Altitude slice: {altLabel}m
      </div>
    </div>
  );
}
