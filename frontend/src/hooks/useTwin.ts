import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { VehicleTwin } from '../types/twin';

export function useTwinSchema() {
  return useQuery({
    queryKey: ['twin-schema'],
    queryFn: api.twins.schema,
    staleTime: Infinity,
  });
}

export function useTwins() {
  return useQuery({
    queryKey: ['twins'],
    queryFn: api.twins.list,
  });
}

export function useTwin(id: string | undefined) {
  return useQuery({
    queryKey: ['twin', id],
    queryFn: () => api.twins.get(id!),
    enabled: !!id,
  });
}

export function useCreateTwin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (twin: Partial<VehicleTwin>) => api.twins.create(twin),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['twins'] }),
  });
}

export function useUpdateTwin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, twin }: { id: string; twin: Partial<VehicleTwin> }) =>
      api.twins.update(id, twin),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['twins'] }),
  });
}

export function useDeleteTwin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.twins.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['twins'] }),
  });
}
