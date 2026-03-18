import React from 'react';
import { clsx } from 'clsx';
import type { TypedParameter } from '../../types/twin';

interface ParameterFieldProps {
  name: string;
  param: TypedParameter;
  onChange: (name: string, value: number | string | boolean) => void;
}

export function ParameterField({ name, param, onChange }: ParameterFieldProps) {
  const hints = param.ui_hints;
  const label = hints?.display_name ?? name.replace(/_/g, ' ');
  const isAdvanced = hints?.advanced ?? false;
  const fieldId = `param-${name}`;

  const hasUncertainty = !!param.uncertainty;

  return (
    <div className={clsx('group', isAdvanced && 'opacity-70 hover:opacity-100 transition-opacity')}>
      <div className="flex items-center justify-between mb-1">
        <label htmlFor={fieldId} className="text-xs font-medium text-white/70">{label}</label>
        <span className="text-[10px] text-white/30 font-mono">{param.units}</span>
      </div>

      <div className="relative">
        {typeof param.value === 'boolean' ? (
          <button
            type="button"
            aria-label={label}
            onClick={() => onChange(name, !param.value)}
            className={clsx(
              'w-10 h-5 rounded-full transition-colors duration-200',
              param.value ? 'bg-gorzen-500' : 'bg-white/10',
            )}
          >
            <div
              className={clsx(
                'w-4 h-4 rounded-full bg-white transition-transform duration-200 ml-0.5',
                param.value && 'translate-x-5',
              )}
            />
          </button>
        ) : typeof param.value === 'string' ? (
          <input
            id={fieldId}
            type="text"
            value={param.value}
            onChange={(e) => onChange(name, e.target.value)}
            className="glass-input text-sm"
          />
        ) : (
          <div className="flex items-center gap-2">
            <input
              id={fieldId}
              type="number"
              value={param.value}
              min={param.constraints?.min_value}
              max={param.constraints?.max_value}
              step={hints?.step ?? 'any'}
              onChange={(e) => onChange(name, parseFloat(e.target.value) || 0)}
              className="glass-input text-sm flex-1 font-mono"
            />
            {param.constraints?.min_value != null && param.constraints?.max_value != null && (
              <input
                type="range"
                aria-label={`${label} slider`}
                min={param.constraints.min_value}
                max={param.constraints.max_value}
                step={hints?.step ?? (param.constraints.max_value - param.constraints.min_value) / 100}
                value={param.value as number}
                onChange={(e) => onChange(name, parseFloat(e.target.value))}
                className="flex-1 accent-gorzen-500"
              />
            )}
          </div>
        )}

        {hasUncertainty && (
          <div className="mt-1 text-[10px] text-white/30 font-mono">
            {param.uncertainty!.distribution}: {JSON.stringify(param.uncertainty!.params)}
          </div>
        )}
      </div>
    </div>
  );
}
