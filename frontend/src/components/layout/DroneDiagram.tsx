import React, { useState, useEffect } from 'react';
import { clsx } from 'clsx';
import {
  Camera,
  Navigation,
  Cog,
  Battery,
  Radio,
  Cpu,
  Fuel,
  Map,
  ChevronDown,
} from 'lucide-react';
import type { SubsystemType } from '../../types/twin';

interface HotspotConfig {
  left: string;
  top: string;
  subsystem: SubsystemType;
  label: string;
  Icon: React.ElementType;
}

interface CoreHotspotConfig {
  left: string;
  top: string;
  subsystems: SubsystemType[];
  label: string;
  Icon: React.ElementType;
}

const DIAGRAM_HOTSPOTS: HotspotConfig[] = [
  { left: '50%', top: '14%', subsystem: 'payload', label: 'Payload', Icon: Camera },
  { left: '50%', top: '50%', subsystem: 'cruise_propulsion', label: 'Cruise', Icon: Navigation },
  { left: '72%', top: '38%', subsystem: 'lift_propulsion', label: 'VTOL', Icon: Cog },
  { left: '28%', top: '38%', subsystem: 'mission_profile', label: 'Mission', Icon: Map },
];

const CORE_HOTSPOT: CoreHotspotConfig = {
  left: '50%',
  top: '42%',
  subsystems: ['energy', 'avionics', 'compute', 'fuel_system'],
  label: 'Core',
  Icon: Battery,
};

const CORE_LABELS: Record<string, string> = {
  energy: 'Battery',
  avionics: 'Avionics',
  compute: 'Compute',
  fuel_system: 'Fuel',
};

const CORE_ICONS: Record<string, React.ElementType> = {
  energy: Battery,
  avionics: Radio,
  compute: Cpu,
  fuel_system: Fuel,
};

interface DroneDiagramProps {
  selected: SubsystemType;
  onSelect: (subsystem: SubsystemType) => void;
  schema?: Record<string, any>;
}

export function DroneDiagram({ selected, onSelect, schema }: DroneDiagramProps) {
  const [coreOpen, setCoreOpen] = useState(false);

  useEffect(() => {
    if (!CORE_HOTSPOT.subsystems.includes(selected)) {
      setCoreOpen(false);
    }
  }, [selected]);

  const labelFor = (sub: SubsystemType) =>
    schema?.subsystems?.[sub]?.label ?? sub.replace(/_/g, ' ');

  return (
    <div className="relative w-full h-full min-h-[480px] flex items-center justify-center">
      {/* Drone image - bird's eye, nose top, tail bottom */}
      <div className="absolute inset-0">
        {/* Base drone: white wireframe tinted to dark blue via brightness + sepia + hue-rotate */}
        <img
          src="/wtf.png"
          alt="VTOL drone bird's eye view"
          className="absolute inset-0 w-full h-full object-contain select-none pointer-events-none"
          style={{ filter: 'brightness(0.55) sepia(1) hue-rotate(190deg) saturate(3)' }}
          draggable={false}
        />
        {/* Animated blue wave overlay that scrolls across the drone */}
        <div
          className="absolute inset-0 pointer-events-none animate-drone-tint"
          style={{ mixBlendMode: 'lighten' }}
          aria-hidden
        />
      </div>

      {/* Hotspot buttons */}
      {DIAGRAM_HOTSPOTS.map(({ left, top, subsystem, label, Icon }) => {
        const isActive = selected === subsystem;
        return (
          <button
            key={`${subsystem}-${left}-${top}`}
            type="button"
            onClick={() => onSelect(subsystem)}
            className={clsx(
              'absolute -translate-x-1/2 -translate-y-1/2 z-10',
              'flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-medium',
              'transition-all duration-200 border backdrop-blur-md outline-none',
              'focus-visible:ring-2 focus-visible:ring-gorzen-500/40',
              isActive
                ? 'bg-gorzen-500/25 text-gorzen-400 border-gorzen-500/40 shadow-lg shadow-gorzen-500/20'
                : 'bg-white/5 text-white/80 border-white/15 hover:bg-white/10 hover:border-white/25',
            )}
            style={{ left, top }}
          >
            <Icon size={14} />
            <span>{labelFor(subsystem)}</span>
          </button>
        );
      })}

      {/* Core hotspot with dropdown */}
      <div className="absolute -translate-x-1/2 -translate-y-1/2 z-10" style={{ left: CORE_HOTSPOT.left, top: CORE_HOTSPOT.top }}>
        <div className="relative">
          <button
            type="button"
            onClick={() => {
              const isCoreSelected = CORE_HOTSPOT.subsystems.includes(selected);
              if (coreOpen) {
                setCoreOpen(false);
              } else if (isCoreSelected) {
                setCoreOpen(true);
              } else {
                onSelect(CORE_HOTSPOT.subsystems[0]);
                setCoreOpen(true);
              }
            }}
            className={clsx(
              'flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-medium',
              'transition-all duration-200 border backdrop-blur-md outline-none',
              'focus-visible:ring-2 focus-visible:ring-gorzen-500/40',
              CORE_HOTSPOT.subsystems.includes(selected)
                ? 'bg-gorzen-500/25 text-gorzen-400 border-gorzen-500/40 shadow-lg shadow-gorzen-500/20'
                : 'bg-white/5 text-white/80 border-white/15 hover:bg-white/10 hover:border-white/25',
            )}
          >
            <CORE_HOTSPOT.Icon size={14} />
            <span>Core</span>
            <ChevronDown size={12} className={clsx('transition-transform', coreOpen && 'rotate-180')} />
          </button>

          {coreOpen && (
            <>
              <div
                className="fixed inset-0 z-20"
                aria-hidden
                onClick={() => setCoreOpen(false)}
              />
              <div
                className="absolute left-1/2 -translate-x-1/2 top-full mt-1.5 z-30 py-1.5 rounded-xl border border-white/12 bg-surface-card backdrop-blur-xl shadow-glass-lg min-w-[140px]"
                role="menu"
                aria-label="Core subsystems"
              >
                {CORE_HOTSPOT.subsystems.map((sub) => {
                  const Icon = CORE_ICONS[sub];
                  const isActive = selected === sub;
                  return (
                    <button
                      key={sub}
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        onSelect(sub);
                        setCoreOpen(false);
                      }}
                      className={clsx(
                        'w-full flex items-center gap-2.5 px-4 py-2 text-sm text-left transition-colors outline-none',
                        'focus-visible:bg-white/10',
                        isActive ? 'bg-gorzen-500/20 text-gorzen-400' : 'text-white/85 hover:bg-white/[0.06]',
                      )}
                    >
                      {Icon && <Icon size={16} />}
                      {CORE_LABELS[sub] ?? labelFor(sub)}
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
