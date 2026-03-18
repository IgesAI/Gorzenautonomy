import { useMutation } from '@tanstack/react-query';
import { api } from '../api/client';
import type { EnvelopeRequest, EnvelopeResponse } from '../types/envelope';

export function useComputeEnvelope() {
  return useMutation({
    mutationFn: ({ twinId, params }: { twinId: string; params: Partial<EnvelopeRequest> }) =>
      api.envelope.compute(twinId, params),
  });
}
