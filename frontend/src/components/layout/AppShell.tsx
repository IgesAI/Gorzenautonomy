import React, { useState, useCallback } from 'react';
import { Plane, Map } from 'lucide-react';
import { DroneDiagram } from './DroneDiagram';
import { GlassPanel } from './GlassPanel';
import { MetadataForm } from '../forms/MetadataForm';
import { EnvelopeChart } from '../visualization/EnvelopeChart';
import { FuelEndurance } from '../visualization/FuelEndurance';
import { BatteryReserve } from '../visualization/BatteryReserve';
import { MissionProb } from '../visualization/MissionProb';
import { IdentConfidence } from '../visualization/IdentConfidence';
import { SensitivityBars } from '../visualization/SensitivityBars';
import { clsx } from 'clsx';
import type { SubsystemType } from '../../types/twin';
import type { EnvelopeResponse } from '../../types/envelope';

interface AppShellProps {
  schema: Record<string, any> | undefined;
  schemaLoading: boolean;
  envelope?: EnvelopeResponse | null;
  computing?: boolean;
  onComputeEnvelope?: (fullParams: Record<string, Record<string, any>>) => void;
}

const SIDE_SUBSYSTEMS: SubsystemType[] = ['airframe', 'mission_profile'];

export function AppShell({ schema, schemaLoading, envelope, computing, onComputeEnvelope }: AppShellProps) {
  const [selectedSubsystem, setSelectedSubsystem] = useState<SubsystemType>('airframe');
  const [paramOverrides, setParamOverrides] = useState<Record<string, Record<string, any>>>({});

  const handleValueChange = useCallback(
    (subsystem: SubsystemType, paramName: string, value: any) => {
      setParamOverrides((prev) => ({
        ...prev,
        [subsystem]: {
          ...(prev[subsystem] ?? {}),
          [paramName]: value,
        },
      }));
    },
    [],
  );

  const subsystemSchema = schema?.subsystems?.[selectedSubsystem];
  const currentOverrides = paramOverrides[selectedSubsystem] ?? {};

  const buildFullParams = useCallback((): Record<string, Record<string, any>> => {
    const subs = schema?.subsystems;
    if (!subs) return paramOverrides;
    const full: Record<string, Record<string, any>> = {};
    const subNames = Object.keys(subs).sort();
    for (const subName of subNames) {
      const subSchema = (subs as Record<string, any>)[subName];
      const params = subSchema?.parameters;
      if (!params) continue;
      full[subName] = {};
      const paramNames = Object.keys(params).sort();
      for (const paramName of paramNames) {
        const paramDef = params[paramName] as { value?: any };
        const override = paramOverrides[subName]?.[paramName];
        const raw = override !== undefined ? override : paramDef?.value;
        full[subName][paramName] = raw;
      }
    }
    return full;
  }, [schema, paramOverrides]);

  const labelFor = (sub: SubsystemType) =>
    schema?.subsystems?.[sub]?.label ?? sub.replace(/_/g, ' ');

  return (
    <div className="flex h-screen bg-surface-dark/50">
      {/* Left: Side panel - Nav + Envelope Output */}
      <aside className="w-80 flex-shrink-0 p-3 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto min-h-0 space-y-3">
          <GlassPanel padding="p-4">
            <div className="flex items-center gap-2.5 mb-5 px-1">
              <div className="w-9 h-9 rounded-xl bg-gorzen-500/15 flex items-center justify-center shadow-card border border-gorzen-500/20">
                <span className="text-gorzen-400 font-bold text-sm">G</span>
              </div>
              <div>
                <div className="text-sm font-semibold text-white/95 tracking-tight">Gorzen</div>
                <div className="text-[10px] text-white/45 font-medium">Digital Twin</div>
              </div>
            </div>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3 px-1">
              General
            </h2>
            <nav className="space-y-1">
              {SIDE_SUBSYSTEMS.map((key) => {
                const isActive = selectedSubsystem === key;
                const Icon = key === 'airframe' ? Plane : Map;
                return (
                  <button
                    key={key}
                    onClick={() => setSelectedSubsystem(key)}
                    className={clsx(
                      'w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all duration-200 outline-none',
                      'focus-visible:ring-2 focus-visible:ring-gorzen-500/30',
                      isActive
                        ? 'bg-gorzen-500/15 text-gorzen-400 border border-gorzen-500/25 shadow-card'
                        : 'text-white/60 hover:text-white/90 hover:bg-white/[0.06] hover:border-white/10 border border-transparent',
                    )}
                  >
                    <Icon size={16} className={isActive ? 'text-gorzen-400' : 'text-white/40'} />
                    <span className="font-medium flex-1 text-left">{labelFor(key)}</span>
                  </button>
                );
              })}
            </nav>
            <div className="mt-4 pt-4 border-t border-white/5">
              <button
                type="button"
                onClick={() => onComputeEnvelope?.(buildFullParams())}
                disabled={computing || !schema}
                className="glass-button w-full text-center text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {computing ? 'Computing...' : 'Compute Envelope'}
              </button>
              {envelope && (
                <div className="mt-2 text-[10px] text-white/35 text-center font-mono">
                  {envelope.computation_time_s.toFixed(1)}s
                </div>
              )}
            </div>
          </GlassPanel>

          {/* Envelope output visualizations */}
          <GlassPanel padding="p-4">
            <MissionProb
              probability={envelope?.mission_completion_probability}
              warnings={envelope?.warnings}
            />
          </GlassPanel>
          <GlassPanel padding="p-4">
            <EnvelopeChart surface={envelope?.speed_altitude_feasibility} />
          </GlassPanel>
          <GlassPanel padding="p-4">
            <FuelEndurance output={envelope?.fuel_endurance} flowRate={envelope?.fuel_flow_rate} />
          </GlassPanel>
          <GlassPanel padding="p-4">
            <BatteryReserve output={envelope?.battery_reserve} />
          </GlassPanel>
          <GlassPanel padding="p-4">
            <IdentConfidence surface={envelope?.identification_confidence} />
          </GlassPanel>
          <GlassPanel padding="p-4">
            <SensitivityBars entries={envelope?.sensitivity ?? []} />
          </GlassPanel>
        </div>
      </aside>

      {/* Center: Drone diagram with hotspots */}
      <main className="flex-1 p-4 min-w-0 flex flex-col overflow-hidden">
        <GlassPanel className="flex-1 min-h-0 overflow-hidden" padding="p-0">
          <div className="w-full h-full min-h-[420px]">
            <DroneDiagram
              selected={selectedSubsystem}
              onSelect={setSelectedSubsystem}
              schema={schema}
            />
          </div>
        </GlassPanel>
      </main>

      {/* Right: Parameter form only */}
      <aside className="w-[380px] flex-shrink-0 flex flex-col p-3 overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          <GlassPanel padding="p-6">
            {schemaLoading ? (
              <div className="flex items-center justify-center h-32">
                <div className="text-white/35 text-sm">Loading...</div>
              </div>
            ) : (
              <MetadataForm
                subsystem={selectedSubsystem}
                schema={subsystemSchema}
                values={currentOverrides}
                onValueChange={handleValueChange}
              />
            )}
          </GlassPanel>
        </div>
      </aside>
    </div>
  );
}
