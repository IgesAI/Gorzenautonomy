export const glassTokens = {
  panel: {
    background: 'rgba(15, 20, 40, 0.75)',
    blur: '20px',
    border: 'rgba(255, 255, 255, 0.12)',
    shadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
    radius: '12px',
  },
  elevated: {
    background: 'rgba(20, 28, 55, 0.85)',
    blur: '40px',
    border: 'rgba(255, 255, 255, 0.15)',
    shadow: '0 12px 40px rgba(0, 0, 0, 0.5)',
    radius: '12px',
  },
  input: {
    background: 'rgba(255, 255, 255, 0.05)',
    border: 'rgba(255, 255, 255, 0.10)',
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
