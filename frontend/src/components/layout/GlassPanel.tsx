import React from 'react';
import { clsx } from 'clsx';

interface GlassPanelProps {
  children: React.ReactNode;
  className?: string;
  elevated?: boolean;
  padding?: string;
}

export function GlassPanel({ children, className, elevated, padding = 'p-4' }: GlassPanelProps) {
  return (
    <div className={clsx(elevated ? 'glass-panel-elevated' : 'glass-panel', padding, className)}>
      {children}
    </div>
  );
}
