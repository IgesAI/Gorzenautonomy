import React from 'react';
import type { CatalogEntry } from '../../types/twin';

interface DropdownCatalogProps {
  entries: CatalogEntry[];
  selected?: string;
  onSelect: (entry: CatalogEntry) => void;
  label: string;
}

export function DropdownCatalog({ entries, selected, onSelect, label }: DropdownCatalogProps) {
  return (
    <div className="mb-4">
      <label htmlFor={`catalog-${label}`} className="text-xs font-medium text-white/70 mb-1 block">{label}</label>
      <select
        id={`catalog-${label}`}
        value={selected ?? ''}
        onChange={(e) => {
          const entry = entries.find((en) => en.entry_id === e.target.value);
          if (entry) onSelect(entry);
        }}
        className="glass-input text-sm"
      >
        <option value="">Custom Configuration</option>
        {entries.map((entry) => (
          <option key={entry.entry_id} value={entry.entry_id}>
            {entry.manufacturer} {entry.model_name}
          </option>
        ))}
      </select>
    </div>
  );
}
