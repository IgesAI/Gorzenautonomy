import type { EnvelopeOutput } from '../../types/envelope';
import { chartStyles } from '../../theme/chartStyles';

interface FuelEnduranceProps {
  output?: EnvelopeOutput | null;
  flowRate?: EnvelopeOutput | null;
}

function getEnduranceColor(hr: number): string {
  if (hr >= 4) return '#10b981';
  if (hr >= 2) return '#f59e0b';
  return '#ef4444';
}

export function FuelEndurance({ output, flowRate }: FuelEnduranceProps) {
  if (!output) {
    return (
      <div>
        <h3 className={chartStyles.title}>Fuel Endurance</h3>
        <div className={chartStyles.emptyState}>No data</div>
      </div>
    );
  }

  const p5 = output.percentiles.p5 ?? output.mean - output.std;
  const p50 = output.percentiles.p50 ?? output.mean;
  const p95 = output.percentiles.p95 ?? output.mean + output.std;

  const hasBand = Math.abs(p5 - p95) > 0.01;
  const barColor = getEnduranceColor(output.mean);
  const scaleMax = Math.max(p95 * 1.2, output.mean * 2, 4);
  const leftPct = Math.max(0, (p5 / scaleMax) * 100);
  const widthPct = hasBand
    ? Math.min(100 - leftPct, ((p95 - p5) / scaleMax) * 100)
    : Math.min(100, (output.mean / scaleMax) * 100);
  const medianPct = Math.min(100, (p50 / scaleMax) * 100);

  return (
    <div>
      <h3 className={`${chartStyles.title} mb-1`}>Fuel Endurance</h3>
      <p className="text-[9px] text-white/35 mb-3">
        Maximum flight time at nominal operating point
      </p>

      <div className="flex items-baseline gap-2 mb-3">
        <span className={chartStyles.valuePrimary} style={{ color: barColor }}>
          {output.mean.toFixed(1)}
        </span>
        <span className={chartStyles.valueSecondary}>hr</span>
        {hasBand && (
          <span className="text-[10px] text-white/35 font-mono ml-auto">
            ±{output.std.toFixed(2)} hr
          </span>
        )}
      </div>

      {/* Bar */}
      <div className="relative h-8 bg-white/[0.04] rounded-lg overflow-hidden mb-2">
        {hasBand ? (
          <>
            <div
              className="absolute h-full rounded-lg"
              style={{
                left: `${leftPct}%`,
                width: `${Math.max(widthPct, 2)}%`,
                background: `${barColor}50`,
              }}
            />
            <div
              className="absolute top-0 h-full w-0.5 bg-white/90"
              style={{ left: `${medianPct}%` }}
            />
          </>
        ) : (
          <div
            className="absolute h-full rounded-lg"
            style={{
              left: 0,
              width: `${Math.max(widthPct, 2)}%`,
              background: `${barColor}70`,
            }}
          />
        )}

        {/* Hour markers */}
        {Array.from({ length: Math.ceil(scaleMax) + 1 }, (_, h) => h)
          .filter((h) => h > 0 && h < scaleMax)
          .map((h) => (
            <div
              key={h}
              className="absolute top-0 h-full w-px bg-white/[0.06]"
              style={{ left: `${(h / scaleMax) * 100}%` }}
            />
          ))}
      </div>

      {hasBand ? (
        <div className="flex justify-between text-[10px] font-mono text-white/45">
          <span>P5: {p5.toFixed(1)}h</span>
          <span className="text-white/60">P50: {p50.toFixed(1)}h</span>
          <span>P95: {p95.toFixed(1)}h</span>
        </div>
      ) : (
        <div className="text-[10px] font-mono text-white/35">
          0 — {scaleMax.toFixed(1)} hr
        </div>
      )}

      {/* Fuel flow rate details */}
      {flowRate && (
        <div className="mt-4 pt-3 border-t border-white/[0.06] space-y-2">
          <div className="flex justify-between text-[11px]">
            <span className="text-white/50">Fuel flow rate</span>
            <span className="font-mono text-white/80">{flowRate.mean.toFixed(0)} g/hr</span>
          </div>
          {flowRate.percentiles.p5 != null && flowRate.percentiles.p95 != null && (
            <div className="flex justify-between text-[10px] text-white/35">
              <span>Range (P5–P95)</span>
              <span className="font-mono">
                {flowRate.percentiles.p5.toFixed(0)} – {flowRate.percentiles.p95.toFixed(0)} g/hr
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
