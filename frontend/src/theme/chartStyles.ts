/** Shared chart styling for consistent, professional visualization. */

export const chartStyles = {
  title: 'text-[11px] font-semibold uppercase tracking-widest text-white/50',
  emptyState: 'flex items-center justify-center text-white/30 text-sm py-8 px-4',
  valuePrimary: 'text-xl font-bold font-mono tabular-nums',
  valueSecondary: 'text-[11px] text-white/50 font-mono',
  label: 'text-[11px] text-white/60',
  grid: 'stroke-white/[0.06]',
  axis: 'fill-white/40 font-mono text-[10px]',
  tick: 'fill-white/35 font-mono text-[9px]',
} as const;
