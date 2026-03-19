/**
 * Design tokens — single source of truth.
 * Values here match the CSS custom properties in index.css.
 */

export const glassTokens = {
  panel: {
    background: 'rgba(15, 20, 40, 0.72)',
    blur: '20px',
    border: 'rgba(255, 255, 255, 0.10)',
    shadow: '0 8px 32px rgba(0, 0, 0, 0.35), 0 1px 0 rgba(255, 255, 255, 0.05) inset',
    radius: '14px',
  },
  elevated: {
    background: 'rgba(20, 28, 55, 0.82)',
    blur: '40px',
    border: 'rgba(255, 255, 255, 0.16)',
    shadow: '0 12px 40px rgba(0, 0, 0, 0.45), 0 1px 0 rgba(255, 255, 255, 0.07) inset',
    radius: '14px',
  },
  input: {
    background: 'rgba(255, 255, 255, 0.04)',
    border: 'rgba(255, 255, 255, 0.08)',
    focusBorder: '#2f7fff',
  },
} as const;

export const colors = {
  accent: { primary: '#2f7fff', secondary: '#56a4ff', muted: 'rgba(47, 127, 255, 0.15)' },
  text: { primary: 'rgba(255, 255, 255, 0.95)', secondary: 'rgba(255, 255, 255, 0.65)', tertiary: 'rgba(255, 255, 255, 0.40)' },
  status: { success: '#10b981', warning: '#f59e0b', danger: '#ef4444', info: '#3b82f6' },
  confidence: {
    high: '#10b981',
    medium: '#f59e0b',
    low: '#ef4444',
  },
} as const;

export function getConfidenceColor(value: number): string {
  if (value >= 0.8) return colors.confidence.high;
  if (value >= 0.5) return colors.confidence.medium;
  return colors.confidence.low;
}
