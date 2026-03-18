import React from 'react';
import { clsx } from 'clsx';
import { getConfidenceColor } from '../../theme/tokens';

interface ModelQualityProps {
  calibrationFreshness?: number;
  dataCoverage?: number;
  posteriorTightness?: number;
}

function QualityBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex justify-between mb-1">
        <span className="text-[10px] text-white/50">{label}</span>
        <span className="text-[10px] font-mono" style={{ color: getConfidenceColor(value) }}>
          {(value * 100).toFixed(0)}%
        </span>
      </div>
      <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${value * 100}%`,
            backgroundColor: getConfidenceColor(value),
          }}
        />
      </div>
    </div>
  );
}

export function ModelQuality({
  calibrationFreshness = 0,
  dataCoverage = 0,
  posteriorTightness = 0,
}: ModelQualityProps) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
        Model Quality
      </h3>
      <div className="space-y-3">
        <QualityBar label="Calibration Freshness" value={calibrationFreshness} />
        <QualityBar label="Data Coverage" value={dataCoverage} />
        <QualityBar label="Posterior Tightness" value={posteriorTightness} />
      </div>
    </div>
  );
}
