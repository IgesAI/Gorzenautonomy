import { FileText, Fuel, Clock, Weight, Zap } from 'lucide-react';
import { clsx } from 'clsx';
import { AIRCRAFT_FLEET } from '../../data/aircraft';
import type { AircraftPreset } from '../../data/aircraft';

interface FleetSelectorProps {
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const FUEL_LABELS: Record<string, string> = {
  gasoline: 'Gasoline',
  heavy_fuel: 'Heavy Fuel (JP5/JP8/Jet-A)',
  electric: 'Electric',
  hybrid_hf: 'Hybrid HF',
  hybrid_gasoline: 'Hybrid Gas',
};

const ARCH_LABELS: Record<string, string> = {
  direct_ice: 'Direct ICE',
  series_hybrid: 'Series Hybrid',
  electric: 'Electric',
};

const ROLE_COLORS: Record<string, string> = {
  inspection: '#3b82f6',
  mapping: '#10b981',
  isr: '#8b5cf6',
  delivery: '#f59e0b',
  sar: '#ef4444',
};

function FuelBadge({ type }: { type: string }) {
  const isHF = type === 'heavy_fuel' || type === 'hybrid_hf';
  return (
    <span
      className={clsx(
        'text-[9px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider',
        isHF
          ? 'bg-amber-500/15 text-amber-400 border border-amber-500/20'
          : 'bg-blue-500/15 text-blue-400 border border-blue-500/20',
      )}
    >
      {isHF ? 'HF' : 'GAS'}
    </span>
  );
}

function AircraftCard({
  aircraft,
  selected,
  onClick,
}: {
  aircraft: AircraftPreset;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full text-left rounded-xl border transition-all duration-200 outline-none',
        'focus-visible:ring-2 focus-visible:ring-gorzen-500/30',
        selected
          ? 'bg-gorzen-500/10 border-gorzen-500/30 shadow-[0_0_16px_rgba(99,102,241,0.08)]'
          : 'bg-white/[0.03] border-white/[0.07] hover:bg-white/[0.06] hover:border-white/15',
      )}
    >
      {/* Header */}
      <div className="p-4 pb-3">
        <div className="flex items-start justify-between gap-2 mb-2">
          <div>
            <div className="flex items-center gap-2">
              <span
                className={clsx(
                  'text-sm font-bold tracking-tight',
                  selected ? 'text-gorzen-400' : 'text-white/90',
                )}
              >
                {aircraft.short_name}
              </span>
              <FuelBadge type={aircraft.fuel_type} />
              {selected && (
                <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-gorzen-500/20 text-gorzen-400 border border-gorzen-500/25 uppercase tracking-wider">
                  Selected
                </span>
              )}
            </div>
            <div className="text-[10px] text-white/35 mt-0.5 font-mono">
              {aircraft.engine.model}
            </div>
          </div>
          <a
            href={aircraft.datasheet_path}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="p-1.5 rounded-lg text-white/25 hover:text-gorzen-400 hover:bg-gorzen-500/10 transition-colors"
            title="Open datasheet"
          >
            <FileText size={12} />
          </a>
        </div>

        {/* Key stats row */}
        <div className="grid grid-cols-4 gap-1.5 mt-3">
          {[
            { Icon: Weight, label: 'MTOW', val: `${aircraft.mtow_kg} kg` },
            { Icon: Weight, label: 'Payload', val: `${aircraft.payload_max_kg} kg` },
            { Icon: Clock, label: 'Endur', val: `${aircraft.endurance_min} min` },
            { Icon: Zap, label: 'Engine', val: `${aircraft.engine.power_kw} kW` },
          ].map(({ Icon, label, val }) => (
            <div
              key={label}
              className="bg-white/[0.04] rounded-lg p-1.5 text-center border border-white/[0.05]"
            >
              <Icon size={9} className="text-white/30 mx-auto mb-0.5" />
              <div className="text-[9px] text-white/30 leading-none">{label}</div>
              <div className="text-[11px] font-mono font-semibold text-white/80 mt-0.5 leading-none">
                {val}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Engine / arch row */}
      <div className="px-4 pb-3 flex items-center gap-3 text-[10px]">
        <Fuel size={10} className="text-white/25 flex-shrink-0" />
        <span className="text-white/40">{FUEL_LABELS[aircraft.fuel_type]}</span>
        <span className="text-white/20">·</span>
        <span className="text-white/35">{ARCH_LABELS[aircraft.propulsion_arch]}</span>
      </div>

      {/* Roles */}
      <div className="px-4 pb-3 flex flex-wrap gap-1">
        {aircraft.roles.map((r) => (
          <span
            key={r}
            className="text-[9px] font-medium px-1.5 py-0.5 rounded-md uppercase tracking-wider"
            style={{
              backgroundColor: `${ROLE_COLORS[r] ?? '#666'}20`,
              color: ROLE_COLORS[r] ?? '#aaa',
              borderColor: `${ROLE_COLORS[r] ?? '#666'}30`,
              borderWidth: 1,
              borderStyle: 'solid',
            }}
          >
            {r}
          </span>
        ))}
      </div>

      {/* Description */}
      <div className="px-4 pb-4 text-[10px] text-white/35 leading-relaxed border-t border-white/[0.04] pt-3">
        {aircraft.description}
      </div>
    </button>
  );
}

export function FleetSelector({ selectedId, onSelect }: FleetSelectorProps) {
  return (
    <div>
      <h2 className="text-[10px] font-semibold uppercase tracking-wider text-white/35 mb-3 px-1">
        <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-white/[0.06] border border-white/[0.10] text-[8px] text-white/40 mr-1.5 font-bold">1</span>
        Select Aircraft
      </h2>
      <div className="space-y-2">
        {AIRCRAFT_FLEET.map((a) => (
          <AircraftCard
            key={a.id}
            aircraft={a}
            selected={selectedId === a.id}
            onClick={() => onSelect(a.id)}
          />
        ))}
      </div>
    </div>
  );
}
