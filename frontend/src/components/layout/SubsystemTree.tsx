import React from 'react';
import { clsx } from 'clsx';
import {
  Plane, Cog, Battery, Radio, Cpu, Camera, Brain, Map, Navigation, Wifi, Fuel
} from 'lucide-react';
import type { SubsystemType } from '../../types/twin';

interface SubsystemTreeProps {
  selected: SubsystemType;
  onSelect: (subsystem: SubsystemType) => void;
  schema?: Record<string, any>;
}

const SUBSYSTEM_ICONS: Record<string, React.ElementType> = {
  airframe: Plane,
  lift_propulsion: Cog,
  cruise_propulsion: Navigation,
  fuel_system: Fuel,
  energy: Battery,
  avionics: Radio,
  compute: Cpu,
  comms: Wifi,
  payload: Camera,
  ai_model: Brain,
  mission_profile: Map,
};

const SUBSYSTEM_ORDER: SubsystemType[] = [
  'airframe', 'cruise_propulsion', 'fuel_system', 'lift_propulsion', 'energy',
  'avionics', 'compute', 'comms', 'payload', 'ai_model', 'mission_profile',
];

export function SubsystemTree({ selected, onSelect, schema }: SubsystemTreeProps) {
  const subsystems = schema?.subsystems;

  return (
    <nav className="space-y-1">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3 px-3">
        Subsystems
      </h2>
      {SUBSYSTEM_ORDER.map((key) => {
        const Icon = SUBSYSTEM_ICONS[key] ?? Cog;
        const isActive = selected === key;
        const label = subsystems?.[key]?.label ?? key.replace(/_/g, ' ');
        const paramCount = subsystems?.[key]?.parameters
          ? Object.keys(subsystems[key].parameters).length
          : 0;

        return (
          <button
            key={key}
            onClick={() => onSelect(key)}
            className={clsx(
              'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150',
              isActive
                ? 'bg-gorzen-500/20 text-gorzen-400 border border-gorzen-500/30'
                : 'text-white/60 hover:text-white/90 hover:bg-white/5 border border-transparent',
            )}
          >
            <Icon size={16} className={isActive ? 'text-gorzen-400' : 'text-white/40'} />
            <span className="font-medium flex-1 text-left">{label}</span>
            {paramCount > 0 && (
              <span className={clsx(
                'text-[10px] font-mono',
                isActive ? 'text-gorzen-400/60' : 'text-white/20',
              )}>
                {paramCount}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
