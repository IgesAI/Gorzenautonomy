import React from 'react';
import { clsx } from 'clsx';
import type { TypedParameter } from '../../types/twin';

interface ParameterFieldProps {
  name: string;
  param: TypedParameter;
  onChange: (name: string, value: number | string | boolean) => void;
}

function formatNumber(value: number, precision?: number): string {
  if (precision == null) return String(value);
  if (Number.isInteger(value) && precision === 0) return String(Math.round(value));
  return value.toFixed(precision);
}

export function ParameterField({ name, param, onChange }: ParameterFieldProps) {
  const hints = param.ui_hints;
  const label = hints?.display_name ?? name.replace(/_/g, ' ');
  const isAdvanced = hints?.advanced ?? false;
  const fieldId = `param-${name}`;

  const hasUncertainty = !!param.uncertainty;
  const allowedValues = param.constraints?.allowed_values as (string | number)[] | undefined;
  const useDropdown = allowedValues != null && allowedValues.length > 0;

  const minVal = param.constraints?.min_value;
  const maxVal = param.constraints?.max_value;
  const hasRange = minVal != null && maxVal != null;
  const stepVal = hints?.step ?? (hasRange ? (maxVal! - minVal!) / 100 : undefined);
  const precision = hints?.precision ?? (stepVal != null && stepVal < 1 ? 2 : 0);

  const clamp = (v: number): number => {
    if (minVal != null && v < minVal) return minVal;
    if (maxVal != null && v > maxVal) return maxVal;
    return v;
  };

  return (
    <div className={clsx('group', isAdvanced && 'opacity-75 hover:opacity-100 transition-opacity')}>
      <div className="flex items-center justify-between mb-1.5">
        <label htmlFor={fieldId} className="text-xs font-medium text-white/75">{label}</label>
        <span className="text-[10px] text-white/35 font-mono">{param.units}</span>
      </div>

      <div className="relative">
        {useDropdown ? (
          <select
            id={fieldId}
            value={String(param.value)}
            onChange={(e) => {
              const v = e.target.value;
              const num = parseFloat(v);
              onChange(name, Number.isNaN(num) ? v : num);
            }}
            className="glass-select"
          >
            {allowedValues.map((opt) => (
              <option key={String(opt)} value={String(opt)}>
                {String(opt)}
              </option>
            ))}
          </select>
        ) : typeof param.value === 'boolean' ? (
          <button
            type="button"
            aria-label={label}
            aria-checked={!!param.value}
            role="switch"
            onClick={() => onChange(name, !param.value)}
            className={clsx(
              'w-10 h-5 rounded-full transition-all duration-200 outline-none',
              'focus-visible:ring-2 focus-visible:ring-gorzen-500/40 focus-visible:ring-offset-1 focus-visible:ring-offset-transparent',
              param.value ? 'bg-gorzen-500 shadow-md' : 'bg-white/10',
            )}
          >
            <div
              className={clsx(
                'w-4 h-4 rounded-full bg-white shadow-md transition-transform duration-200 ml-0.5',
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
          <div className="space-y-2">
            <div className={clsx('flex items-center gap-2', hasRange && 'flex-wrap')}>
              <input
                id={fieldId}
                type="number"
                value={param.value}
                min={minVal}
                max={maxVal}
                step={stepVal ?? 'any'}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  onChange(name, Number.isNaN(v) ? 0 : clamp(v));
                }}
                className={clsx(
                  'glass-input text-sm font-mono tabular-nums',
                  hasRange ? 'w-20 min-w-[5rem]' : 'w-full',
                )}
              />
              {hasRange && (
                <span className="text-[10px] text-white/35 font-mono">
                  range: {formatNumber(minVal!, precision)} – {formatNumber(maxVal!, precision)} {param.units}
                </span>
              )}
            </div>
            {hasRange && (
              <input
                type="range"
                aria-label={`${label} slider`}
                min={minVal}
                max={maxVal}
                step={stepVal ?? (maxVal! - minVal!) / 100}
                value={Math.max(minVal!, Math.min(maxVal!, param.value as number))}
                onChange={(e) => onChange(name, parseFloat(e.target.value))}
                className="glass-slider w-full"
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
