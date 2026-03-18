import React, { useState } from 'react';
import { AppShell } from './components/layout/AppShell';
import { useTwinSchema } from './hooks/useTwin';
import type { EnvelopeResponse } from './types/envelope';

export default function App() {
  const { data: schema, isLoading: schemaLoading } = useTwinSchema();
  const [envelope, setEnvelope] = useState<EnvelopeResponse | null>(null);

  const handleComputeEnvelope = async () => {
    setEnvelope({
      speed_altitude_feasibility: {
        x_label: 'Speed (m/s)',
        y_label: 'Altitude (m)',
        z_label: 'Feasible',
        x_values: Array.from({ length: 20 }, (_, i) => i * 2),
        y_values: Array.from({ length: 20 }, (_, i) => 10 + i * 7),
        z_mean: Array.from({ length: 20 }, (_, yi) =>
          Array.from({ length: 20 }, (_, xi) =>
            xi < 15 && yi > 2 && yi < 17 ? 1.0 : 0.0,
          ),
        ),
        z_p5: Array.from({ length: 20 }, () => Array.from({ length: 20 }, () => 0)),
        z_p95: Array.from({ length: 20 }, () => Array.from({ length: 20 }, () => 1)),
        feasible_mask: Array.from({ length: 20 }, (_, yi) =>
          Array.from({ length: 20 }, (_, xi) =>
            xi < 15 && yi > 2 && yi < 17,
          ),
        ),
      },
      safe_inspection_speed: {
        mean: 12.5, std: 1.8,
        percentiles: { p5: 9.5, p25: 11.2, p50: 12.5, p75: 13.8, p95: 15.5 },
        units: 'm/s',
      },
      battery_reserve: {
        mean: 18.3, std: 2.1,
        percentiles: { p5: 14.8, p25: 16.9, p50: 18.3, p75: 19.7, p95: 21.8 },
        units: 'min',
      },
      identification_confidence: {
        x_label: 'Speed (m/s)',
        y_label: 'Altitude (m)',
        z_label: 'Identification Confidence',
        x_values: Array.from({ length: 20 }, (_, i) => i * 2),
        y_values: Array.from({ length: 20 }, (_, i) => 10 + i * 7),
        z_mean: Array.from({ length: 20 }, (_, yi) =>
          Array.from({ length: 20 }, (_, xi) =>
            Math.max(0, 0.95 - xi * 0.03 - Math.abs(yi - 10) * 0.01),
          ),
        ),
        z_p5: Array.from({ length: 20 }, () => Array.from({ length: 20 }, () => 0)),
        z_p95: Array.from({ length: 20 }, () => Array.from({ length: 20 }, () => 1)),
      },
      mission_completion_probability: 0.87,
      sensitivity: [
        { parameter_name: 'wind_speed_ms', contribution_pct: 32 },
        { parameter_name: 'bsfc_cruise_g_kwh', contribution_pct: 24 },
        { parameter_name: 'mass_total_kg', contribution_pct: 18 },
        { parameter_name: 'cd0', contribution_pct: 12 },
        { parameter_name: 'temperature_c', contribution_pct: 8 },
        { parameter_name: 'fuel_reserve_pct', contribution_pct: 6 },
      ],
      computation_time_s: 1.2,
    });
  };

  return (
    <AppShell
      schema={schema}
      schemaLoading={schemaLoading}
      envelope={envelope}
      onComputeEnvelope={handleComputeEnvelope}
    />
  );
}
