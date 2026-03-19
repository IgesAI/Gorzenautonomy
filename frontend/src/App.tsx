import React, { useState, useCallback } from 'react';
import { AppShell } from './components/layout/AppShell';
import { useTwinSchema } from './hooks/useTwin';
import { api } from './api/client';
import type { EnvelopeResponse } from './types/envelope';

export default function App() {
  const { data: schema, isLoading: schemaLoading } = useTwinSchema();
  const [envelope, setEnvelope] = useState<EnvelopeResponse | null>(null);
  const [computing, setComputing] = useState(false);

  const handleComputeEnvelope = useCallback(
    async (fullParams: Record<string, Record<string, any>> = {}) => {
      setComputing(true);
      try {
        const result = await api.envelope.computeDefault({
          twin_id: 'default',
          speed_range_ms: [0.5, 35.0],
          altitude_range_m: [10.0, 200.0],
          grid_resolution: 20,
          param_overrides: fullParams,
        });
        setEnvelope(result);
      } catch (err) {
        console.error('Envelope computation failed:', err);
      } finally {
        setComputing(false);
      }
    },
    []
  );

  return (
    <AppShell
      schema={schema}
      schemaLoading={schemaLoading}
      envelope={envelope}
      computing={computing}
      onComputeEnvelope={handleComputeEnvelope}
    />
  );
}
