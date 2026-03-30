import type { EnvelopeOutput } from '../../types/envelope';
import { chartStyles } from '../../theme/chartStyles';

interface BatteryReserveProps {
  output?: EnvelopeOutput | null;
}

function getBarColor(ratio: number): string {
  if (ratio >= 0.5) return '#10b981';
  if (ratio >= 0.25) return '#f59e0b';
  return '#ef4444';
}

export function BatteryReserve({ output }: BatteryReserveProps) {
  if (!output) {
    return (
      <div>
        <h3 className={chartStyles.title}>Battery Reserve (VTOL)</h3>
        <div className={chartStyles.emptyState}>No data</div>
      </div>
    );
  }

  const p5 = output.percentiles.p5 ?? output.mean - output.std;
  const p50 = output.percentiles.p50 ?? output.mean;
  const p95 = output.percentiles.p95 ?? output.mean + output.std;

  const hasBand = Math.abs(p5 - p95) > 0.01;
  const scaleMax = Math.max(p95 * 1.3, output.mean * 2, 10);
  const barColor = getBarColor(output.mean / scaleMax);

  const leftPct = Math.max(0, (p5 / scaleMax) * 100);
  const widthPct = hasBand
    ? Math.min(100 - leftPct, ((p95 - p5) / scaleMax) * 100)
    : Math.min(100, (output.mean / scaleMax) * 100);
  const medianPct = Math.min(100, (p50 / scaleMax) * 100);

  return (
    <div>
      <h3 className={`${chartStyles.title} mb-1`}>Battery Reserve (VTOL)</h3>
      <p className="text-[9px] text-white/35 mb-3">
        Electrical endurance at nominal operating point
      </p>

      <div className="flex items-baseline gap-2 mb-3">
        <span className={chartStyles.valuePrimary} style={{ color: barColor }}>
          {output.mean.toFixed(1)}
        </span>
        <span className={chartStyles.valueSecondary}>{output.units || 'min'}</span>
        {hasBand && (
          <span className="text-[10px] text-white/35 font-mono ml-auto">
            ±{output.std.toFixed(1)}
          </span>
        )}
      </div>

      {/* Bar chart */}
      <div className="relative h-7 bg-white/[0.04] rounded-lg overflow-hidden mb-2">
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
        {/* Scale markers */}
        {[0.25, 0.5, 0.75].map((t) => (
          <div
            key={t}
            className="absolute top-0 h-full w-px bg-white/[0.06]"
            style={{ left: `${t * 100}%` }}
          />
        ))}
      </div>

      {hasBand ? (
        <div className="flex justify-between text-[10px] font-mono text-white/45">
          <span>P5: {p5.toFixed(1)}</span>
          <span className="text-white/60">P50: {p50.toFixed(1)}</span>
          <span>P95: {p95.toFixed(1)}</span>
        </div>
      ) : (
        <div className="text-[10px] font-mono text-white/35">
          0 — {scaleMax.toFixed(0)} {output.units || 'min'}
        </div>
      )}
    </div>
  );
}
