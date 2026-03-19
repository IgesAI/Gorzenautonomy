import React, { useState, useCallback } from 'react';
import type { SubsystemType } from '../../types/twin';
import { ParameterField } from './ParameterField';
import { OverrideDrawer } from './OverrideDrawer';

interface SubsystemSchema {
  label: string;
  description: string;
  parameters: Record<string, any>;
}

interface MetadataFormProps {
  subsystem: SubsystemType;
  schema: SubsystemSchema | undefined;
  values: Record<string, any>;
  onValueChange: (subsystem: SubsystemType, paramName: string, value: any) => void;
}

export function MetadataForm({ subsystem, schema, values, onValueChange }: MetadataFormProps) {
  if (!schema) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="text-white/30 text-sm">Loading schema...</div>
      </div>
    );
  }

  const params = schema.parameters;

  const mergedParams: Record<string, any> = {};
  for (const [name, paramDef] of Object.entries(params)) {
    mergedParams[name] = {
      ...paramDef,
      value: values[name] !== undefined ? values[name] : paramDef.value,
    };
  }

  const basicEntries = Object.entries(mergedParams).filter(
    ([, p]) => !p.ui_hints?.advanced,
  );
  const allEntries = mergedParams;

  const groups = new Map<string, [string, any][]>();
  for (const [name, param] of basicEntries) {
    const group = param.ui_hints?.group ?? 'general';
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group)!.push([name, param]);
  }

  const handleChange = useCallback(
    (name: string, value: any) => {
      onValueChange(subsystem, name, value);
    },
    [subsystem, onValueChange],
  );

  return (
    <div>
      <h2 className="text-lg font-semibold text-white/95 mb-1 tracking-tight">
        {schema.label}
      </h2>
      <p className="text-xs text-white/45 mb-6 leading-relaxed">
        {schema.description}
      </p>

      {Array.from(groups.entries()).map(([group, fields]) => (
        <div key={group} className="mb-8">
          <h3 className="text-[11px] font-semibold uppercase tracking-widest text-white/35 mb-3">
            {group.replace(/_/g, ' ')}
          </h3>
          <div className="grid grid-cols-2 gap-x-5 gap-y-4">
            {fields.map(([name, param]) => (
              <ParameterField
                key={name}
                name={name}
                param={param}
                onChange={handleChange}
              />
            ))}
          </div>
        </div>
      ))}

      <OverrideDrawer
        title="Advanced Overrides"
        params={allEntries}
        onChange={handleChange}
      />
    </div>
  );
}
