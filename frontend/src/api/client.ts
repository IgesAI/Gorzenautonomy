const API_BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const error = await res.text().catch(() => 'Unknown error');
    throw new Error(`API ${res.status}: ${error}`);
  }
  return res.json();
}

export const api = {
  twins: {
    schema: () => request<any>('/twins/schema'),
    list: () => request<any[]>('/twins'),
    get: (id: string) => request<any>(`/twins/${id}`),
    create: (twin: any) => request<any>('/twins/', { method: 'POST', body: JSON.stringify(twin) }),
    update: (id: string, twin: any) => request<any>(`/twins/${id}`, { method: 'PUT', body: JSON.stringify(twin) }),
    delete: (id: string) => request<any>(`/twins/${id}`, { method: 'DELETE' }),
  },
  envelope: {
    compute: (twinId: string, params: any) =>
      request<any>(`/twins/${twinId}/envelope`, { method: 'POST', body: JSON.stringify(params) }),
    computeDefault: (params: any) =>
      request<any>('/twins/default/envelope', { method: 'POST', body: JSON.stringify(params) }),
  },
  mission: {
    plan: (twinId: string, params: any) =>
      request<any>(`/twins/${twinId}/mission`, { method: 'POST', body: JSON.stringify(params) }),
  },
  catalog: {
    list: () => request<any[]>('/catalog/'),
    byType: (type: string) => request<any[]>(`/catalog/${type}`),
  },
  calibration: {
    status: (twinId: string) => request<any>(`/calibration/${twinId}/status`),
    missions: () => request<any[]>('/calibration/missions'),
  },
  environment: {
    solar: (lat: number, lon: number, alt?: number) =>
      request<any>(`/environment/solar?latitude=${lat}&longitude=${lon}&altitude_m=${alt ?? 0}`),
    weather: (lat: number, lon: number, elev?: number) =>
      request<any>(`/environment/weather?latitude=${lat}&longitude=${lon}&elevation_m=${elev ?? 0}`),
    terrain: (lat: number, lon: number) =>
      request<any>(`/environment/terrain?latitude=${lat}&longitude=${lon}`),
    terrainProfile: (points: number[][]) =>
      request<any>('/environment/terrain/profile', { method: 'POST', body: JSON.stringify({ points }) }),
    niirs: () => request<any>('/environment/niirs'),
    niirsLevel: (level: number) => request<any>(`/environment/niirs/${level}`),
    modelChain: (speed_ms: number, altitude_m: number) =>
      request<any>('/environment/model-chain', {
        method: 'POST',
        body: JSON.stringify({ speed_ms, altitude_m }),
      }),
  },
};
