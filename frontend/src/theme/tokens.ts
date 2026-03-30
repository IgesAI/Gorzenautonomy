/**
 * Design tokens — single source of truth.
 * Values here match the CSS custom properties in index.css.
 * Theme: black & white / monochrome.
 */

export const glassTokens = {
  panel: {
    background: 'rgba(8, 8, 8, 0.80)',
    blur: '20px',
    border: 'rgba(255, 255, 255, 0.08)',
    shadow: '0 8px 32px rgba(0, 0, 0, 0.45), 0 1px 0 rgba(255, 255, 255, 0.03) inset',
    radius: '14px',
  },
  elevated: {
    background: 'rgba(14, 14, 14, 0.88)',
    blur: '40px',
    border: 'rgba(255, 255, 255, 0.14)',
    shadow: '0 12px 40px rgba(0, 0, 0, 0.55), 0 1px 0 rgba(255, 255, 255, 0.05) inset',
    radius: '14px',
  },
  input: {
    background: 'rgba(255, 255, 255, 0.03)',
    border: 'rgba(255, 255, 255, 0.06)',
    focusBorder: '#ffffff',
  },
} as const;

export const colors = {
  accent: { primary: '#ffffff', secondary: '#d4d4d4', muted: 'rgba(255, 255, 255, 0.08)' },
  text: { primary: 'rgba(255, 255, 255, 0.95)', secondary: 'rgba(255, 255, 255, 0.65)', tertiary: 'rgba(255, 255, 255, 0.40)' },
  status: { success: '#10b981', warning: '#f59e0b', danger: '#ef4444', info: '#a3a3a3' },
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
