import React, { useState } from 'react';
import { clsx } from 'clsx';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { TypedParameter } from '../../types/twin';
import { ParameterField } from './ParameterField';

interface OverrideDrawerProps {
  title: string;
  params: Record<string, TypedParameter>;
  onChange: (name: string, value: number | string | boolean) => void;
}

export function OverrideDrawer({ title, params, onChange }: OverrideDrawerProps) {
  const [open, setOpen] = useState(false);

  const advancedParams = Object.entries(params).filter(
    ([, p]) => p.ui_hints?.advanced === true,
  );

  if (advancedParams.length === 0) return null;

  return (
    <div className="mt-6 pt-4 border-t border-white/[0.06]">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex items-center gap-2 text-xs font-medium text-white/45 hover:text-white/70 transition-colors duration-150 outline-none focus-visible:text-white/70"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {title} ({advancedParams.length} parameters)
      </button>

      {open && (
        <div className="mt-4 space-y-4 pl-3 border-l-2 border-gorzen-500/20">
          {advancedParams.map(([name, param]) => (
            <ParameterField key={name} name={name} param={param} onChange={onChange} />
          ))}
        </div>
      )}
    </div>
  );
}
