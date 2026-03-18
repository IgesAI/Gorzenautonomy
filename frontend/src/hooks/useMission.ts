import { useMutation } from '@tanstack/react-query';
import { api } from '../api/client';
import type { MissionPlanRequest, MissionPlanResponse } from '../types/mission';

export function usePlanMission() {
  return useMutation({
    mutationFn: ({ twinId, params }: { twinId: string; params: MissionPlanRequest }) =>
      api.mission.plan(twinId, params),
  });
}
