/**
 * Glass material system with WCAG contrast enforcement.
 *
 * Ensures minimum 4.5:1 contrast ratio for normal text against glass backgrounds.
 */

export function relativeLuminance(r: number, g: number, b: number): number {
  const [rs, gs, bs] = [r, g, b].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
}

export function contrastRatio(l1: number, l2: number): number {
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

export function meetsWCAG_AA(
  textR: number, textG: number, textB: number,
  bgR: number, bgG: number, bgB: number,
): boolean {
  const textLum = relativeLuminance(textR, textG, textB);
  const bgLum = relativeLuminance(bgR, bgG, bgB);
  return contrastRatio(textLum, bgLum) >= 4.5;
}

export const glassMaterials = {
  standard: {
    className: 'glass-panel',
    style: {
      background: 'rgba(15, 20, 40, 0.75)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      border: '1px solid rgba(255, 255, 255, 0.12)',
      boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
      borderRadius: '12px',
    },
  },
  elevated: {
    className: 'glass-panel-elevated',
    style: {
      background: 'rgba(20, 28, 55, 0.85)',
      backdropFilter: 'blur(40px)',
      WebkitBackdropFilter: 'blur(40px)',
      border: '1px solid rgba(255, 255, 255, 0.15)',
      boxShadow: '0 12px 40px rgba(0, 0, 0, 0.5)',
      borderRadius: '12px',
    },
  },
  subtle: {
    className: '',
    style: {
      background: 'rgba(255, 255, 255, 0.03)',
      backdropFilter: 'blur(8px)',
      WebkitBackdropFilter: 'blur(8px)',
      border: '1px solid rgba(255, 255, 255, 0.06)',
      borderRadius: '8px',
    },
  },
} as const;
