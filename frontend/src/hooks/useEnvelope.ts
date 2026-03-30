import { useMutation } from '@tanstack/react-query';
import { api } from '../api/client';
import type { EnvelopeRequest, EnvelopeResponse } from '../types/envelope';

export function useComputeEnvelope() {
  return useMutation({
    mutationFn: ({ twinId, params }: { twinId: string; params: Partial<EnvelopeRequest> }) =>
      api.envelope.compute(twinId, {
        speed_range_ms: [0.5, 35.0],
        altitude_range_m: [10.0, 200.0],
        grid_resolution: 20,
        uq_method: 'monte_carlo',
        mc_samples: 1000,
        ...params,
      }),
  });
}
