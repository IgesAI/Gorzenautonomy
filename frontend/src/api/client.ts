import type { EndurancePreview } from '../types/api';
import type {
  CalibrationStatus,
  CatalogEntry,
  DroneTransferResponse,
  LogUploadResponse,
  MissionAnalysis,
  ModelChainResponse,
  NiirsLevel,
  SolarResponse,
  TerrainProfileResponse,
  TerrainResponse,
  TelemetrySnapshot,
  TelemetryStatus,
  TelemetryLinkProfile,
  TwinSchemaResponse,
  VehicleTwin,
  WaypointsResponse,
  WeatherResponse,
} from '../types/api';
import type { EnvelopeRequest, EnvelopeResponse } from '../types/envelope';

const API_BASE = '/api';

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  try {
    const t = localStorage.getItem('gorzen_token');
    if (t) headers['Authorization'] = `Bearer ${t}`;
  } catch {
    /* ignore */
  }
  return headers;
}

async function request<T = unknown>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...options?.headers },
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
    schema: () => request<TwinSchemaResponse>('/twins/schema'),
    list: () => request<VehicleTwin[]>('/twins/'),
    get: (id: string) => request<VehicleTwin>(`/twins/${encodeURIComponent(id)}`),
    create: (twin: Partial<VehicleTwin>) =>
      request<VehicleTwin>('/twins/', { method: 'POST', body: JSON.stringify(twin) }),
    update: (id: string, twin: Partial<VehicleTwin>) =>
      request<VehicleTwin>(`/twins/${encodeURIComponent(id)}`, {
        method: 'PUT',
        body: JSON.stringify(twin),
      }),
    delete: (id: string) =>
      request<{ status: string }>(`/twins/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  },
  envelope: {
    compute: (twinId: string, params: Omit<EnvelopeRequest, 'twin_id'>) => {
      const path =
        twinId === 'default'
          ? '/twins/default/envelope'
          : `/twins/${encodeURIComponent(twinId)}/envelope`;
      return request<EnvelopeResponse>(path, {
        method: 'POST',
        body: JSON.stringify({ ...params, twin_id: twinId }),
      });
    },
    endurancePreview: (twinId: string, speed_ms = 15, altitude_m = 50) =>
      request<EndurancePreview>(
        `/twins/${encodeURIComponent(twinId)}/endurance-preview?speed_ms=${speed_ms}&altitude_m=${altitude_m}`,
      ),
  },
  mission: {
    plan: <T extends object>(twinId: string, params: T) =>
      request<Record<string, unknown>>(`/twins/${encodeURIComponent(twinId)}/mission`, {
        method: 'POST',
        body: JSON.stringify(params),
      }),
  },
  catalog: {
    list: () => request<CatalogEntry[]>('/catalog/'),
    byType: (type: string) =>
      request<CatalogEntry[]>(`/catalog/${encodeURIComponent(type)}`),
  },
  calibration: {
    status: (twinId: string) =>
      request<CalibrationStatus>(`/calibration/${encodeURIComponent(twinId)}/status`),
    missions: () => request<CalibrationStatus[]>('/calibration/missions'),
  },
  environment: {
    solar: (lat: number, lon: number, alt?: number) =>
      request<SolarResponse>(
        `/environment/solar?latitude=${lat}&longitude=${lon}&altitude_m=${alt ?? 0}`,
      ),
    weather: (lat: number, lon: number, elev?: number) =>
      request<WeatherResponse>(
        `/environment/weather?latitude=${lat}&longitude=${lon}&elevation_m=${elev ?? 0}`,
      ),
    terrain: (lat: number, lon: number) =>
      request<TerrainResponse>(
        `/environment/terrain?latitude=${lat}&longitude=${lon}`,
      ),
    terrainProfile: (points: number[][]) =>
      request<TerrainProfileResponse>('/environment/terrain/profile', {
        method: 'POST',
        body: JSON.stringify({ points }),
      }),
    niirs: () => request<{ levels: NiirsLevel[] }>('/environment/niirs'),
    niirsLevel: (level: number) =>
      request<NiirsLevel>(`/environment/niirs/${level}`),
    modelChain: (speed_ms: number, altitude_m: number) =>
      request<ModelChainResponse>('/environment/model-chain', {
        method: 'POST',
        body: JSON.stringify({ speed_ms, altitude_m }),
      }),
  },
  telemetry: {
    connect: (address: string, options?: { link_profile?: TelemetryLinkProfile }) =>
      request<TelemetryStatus>('/telemetry/connect', {
        method: 'POST',
        body: JSON.stringify({
          address,
          link_profile: options?.link_profile ?? 'default',
        }),
      }),
    disconnect: () => request<{ status: string }>('/telemetry/disconnect', { method: 'POST' }),
    status: () => request<TelemetryStatus>('/telemetry/status'),
    snapshot: () => request<TelemetrySnapshot>('/telemetry/snapshot'),
    paramMap: () => request<{ mappings: import('../types/api').ParamMapping[] }>('/telemetry/params/map'),
    twinToPx4: (params: Record<string, Record<string, unknown>>) =>
      request<Record<string, unknown>>('/telemetry/params/to-px4', {
        method: 'POST',
        body: JSON.stringify({ params }),
      }),
    px4ToTwin: (params: Record<string, unknown>) =>
      request<Record<string, unknown>>('/telemetry/params/from-px4', {
        method: 'POST',
        body: JSON.stringify({ params }),
      }),
    logTopics: () => request<{ topics: string[] }>('/telemetry/logs/topics'),
    uploadLog: (file: File): Promise<LogUploadResponse & Record<string, any>> => {
      const form = new FormData();
      form.append('file', file);
      return fetch(`${API_BASE}/telemetry/logs/upload`, {
        method: 'POST',
        body: form,
        headers: authHeaders(),
      }).then((r) => {
        if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
        return r.json();
      });
    },
    uploadCalibration: (file: File): Promise<Record<string, any>> => {
      const form = new FormData();
      form.append('file', file);
      return fetch(`${API_BASE}/telemetry/logs/calibration`, {
        method: 'POST',
        body: form,
        headers: authHeaders(),
      }).then((r) => {
        if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
        return r.json();
      });
    },
    analyzeLog: (file: File): Promise<Record<string, any>> => {
      const form = new FormData();
      form.append('file', file);
      return fetch(`${API_BASE}/telemetry/logs/analyze`, {
        method: 'POST',
        body: form,
        headers: authHeaders(),
      }).then((r) => {
        if (!r.ok) throw new Error(`Analysis failed: ${r.status}`);
        return r.json();
      });
    },
    listLogs: () => request<Record<string, any>[]>('/telemetry-logs/'),
    createCalibrationFromLog: (logId: string, twinId: string) =>
      request<Record<string, any>>('/telemetry/logs/create-calibration', {
        method: 'POST',
        body: JSON.stringify({ log_id: logId, twin_id: twinId }),
      }),
    syncParamsToFC: (params: Record<string, Record<string, unknown>>) =>
      request<{ synced: number; failed: number; params: Record<string, boolean> }>(
        '/telemetry/params/sync-to-fc',
        { method: 'POST', body: JSON.stringify({ params }) },
      ),
    readParamsFromFC: () =>
      request<{ fc_param_count: number; twin_params: Record<string, Record<string, unknown>>; subsystems_affected: string[] }>(
        '/telemetry/params/read-from-fc',
        { method: 'POST' },
      ),
    uploadGeofence: (polygon: number[][]) =>
      request<{ success: boolean; vertices: number; message: string }>(
        '/telemetry/geofence/upload',
        { method: 'POST', body: JSON.stringify({ polygon }) },
      ),
  },
  missionPlan: {
    getWaypoints: () => request<WaypointsResponse>('/mission-plan/waypoints'),
    setWaypoints: (waypoints: Record<string, unknown>[]) =>
      request<WaypointsResponse>('/mission-plan/waypoints', {
        method: 'POST',
        body: JSON.stringify({ waypoints }),
      }),
    addWaypoint: (wp: Record<string, unknown>) =>
      request<WaypointsResponse>('/mission-plan/waypoints/add', {
        method: 'POST',
        body: JSON.stringify(wp),
      }),
    removeWaypoint: (index: number) =>
      request<{ status: string }>(`/mission-plan/waypoints/${index}`, { method: 'DELETE' }),
    clearWaypoints: () =>
      request<{ status: string }>('/mission-plan/waypoints', { method: 'DELETE' }),
    analysis: () => request<MissionAnalysis>('/mission-plan/analysis'),
    geojson: () => request<Record<string, unknown>>('/mission-plan/geojson'),
    uploadToDrone: (address: string = 'udp://:14540') =>
      request<DroneTransferResponse>('/mission-plan/upload', {
        method: 'POST',
        body: JSON.stringify({ address }),
      }),
    downloadFromDrone: (address: string = 'udp://:14540') =>
      request<DroneTransferResponse>('/mission-plan/download', {
        method: 'POST',
        body: JSON.stringify({ address }),
      }),
    importPlan: (planData: Record<string, unknown>) =>
      request<{ imported: boolean; waypoint_count: number; estimated_distance_m: number; estimated_duration_s: number }>(
        '/mission-plan/import/plan',
        { method: 'POST', body: JSON.stringify(planData) },
      ),
  },
  auth: {
    login: (username: string, password: string) => {
      const form = new URLSearchParams();
      form.set('username', username);
      form.set('password', password);
      return fetch(`${API_BASE}/auth/token`, {
        method: 'POST',
        body: form,
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      }).then((r) => {
        if (!r.ok) throw new Error(`Login failed: ${r.status}`);
        return r.json() as Promise<{ access_token: string; token_type: string }>;
      });
    },
  },
};
