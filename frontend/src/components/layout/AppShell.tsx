import React, { useState, useCallback } from 'react';
import { SubsystemTree } from './SubsystemTree';
import { GlassPanel } from './GlassPanel';
import { MetadataForm } from '../forms/MetadataForm';
import { EnvelopeChart } from '../visualization/EnvelopeChart';
import { FuelEndurance } from '../visualization/FuelEndurance';
import { BatteryReserve } from '../visualization/BatteryReserve';
import { MissionProb } from '../visualization/MissionProb';
import { IdentConfidence } from '../visualization/IdentConfidence';
import { SensitivityBars } from '../visualization/SensitivityBars';
import type { SubsystemType } from '../../types/twin';
import type { EnvelopeResponse } from '../../types/envelope';

interface AppShellProps {
  schema: Record<string, any> | undefined;
  schemaLoading: boolean;
  envelope?: EnvelopeResponse | null;
  computing?: boolean;
  onComputeEnvelope?: () => void;
}

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

  return (
    <div className="flex h-screen">
      {/* Left: Subsystem Tree */}
      <aside className="w-56 flex-shrink-0 p-3">
        <GlassPanel className="h-full overflow-y-auto" padding="p-3">
          <div className="flex items-center gap-2 mb-6 px-2">
            <div className="w-8 h-8 rounded-lg bg-gorzen-500/20 flex items-center justify-center">
              <span className="text-gorzen-400 font-bold text-sm">G</span>
            </div>
            <div>
              <div className="text-sm font-semibold text-white/90">Gorzen</div>
              <div className="text-[10px] text-white/40">Digital Twin</div>
            </div>
          </div>
          <SubsystemTree selected={selectedSubsystem} onSelect={setSelectedSubsystem} schema={schema} />
          <div className="mt-6 px-2">
            <button
              type="button"
              onClick={onComputeEnvelope}
              disabled={computing}
              className="glass-button w-full text-center text-sm disabled:opacity-50"
            >
              {computing ? 'Computing...' : 'Compute Envelope'}
            </button>
            {envelope && (
              <div className="mt-2 text-[10px] text-white/30 text-center font-mono">
                {envelope.computation_time_s.toFixed(1)}s
              </div>
            )}
          </div>
        </GlassPanel>
      </aside>

      {/* Center: Forms */}
      <main className="flex-1 p-3 overflow-y-auto">
        <GlassPanel className="min-h-full" padding="p-5">
          {schemaLoading ? (
            <div className="flex items-center justify-center h-48">
              <div className="text-white/30 text-sm">Loading from backend...</div>
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
      </main>

      {/* Right: Visualization */}
      <aside className="w-[420px] flex-shrink-0 p-3 overflow-y-auto space-y-4">
        <GlassPanel padding="p-5">
          <MissionProb
            probability={envelope?.mission_completion_probability}
            warnings={envelope?.warnings}
          />
        </GlassPanel>
        <GlassPanel padding="p-5">
          <EnvelopeChart surface={envelope?.speed_altitude_feasibility} />
        </GlassPanel>
        <GlassPanel padding="p-5">
          <FuelEndurance output={envelope?.fuel_endurance} flowRate={envelope?.fuel_flow_rate} />
        </GlassPanel>
        <GlassPanel padding="p-5">
          <BatteryReserve output={envelope?.battery_reserve} />
        </GlassPanel>
        <GlassPanel padding="p-5">
          <IdentConfidence surface={envelope?.identification_confidence} />
        </GlassPanel>
        <GlassPanel padding="p-5">
          <SensitivityBars entries={envelope?.sensitivity ?? []} />
        </GlassPanel>
      </aside>
    </div>
  );
}
