import type { EndurancePreview } from '../types/api';
import type {
  CalibrationStatus,
  CatalogEntry,
  DroneTransferResponse,
  FcHealthSummary,
  FcLogDownload,
  FcLogList,
  GeofenceUploadRequest,
  LogUploadResponse,
  MissionAnalysis,
  MissionUploadResponse,
  MissionValidateRequest,
  MissionValidateResponse,
  ModelChainResponse,
  NiirsLevel,
  PreflightSummary,
  SolarResponse,
  TerrainProfileResponse,
  TerrainResponse,
  TelemetrySnapshot,
  TelemetryStatus,
  TelemetryLinkProfile,
  TwinSchemaResponse,
  VehicleTwin,
  WeatherResponse,
  WaypointsResponse,
} from '../types/api';
import type { EnvelopeRequest, EnvelopeResponse } from '../types/envelope';

const API_BASE = '/api';
export const TOKEN_STORAGE_KEY = 'gorzen_token';

/** Default dev token. If the backend sets ``GORZEN_DEV_WS_TOKEN=dev-local-token``
 * the WebSocket handshake "just works" without the operator touching the login
 * dialog. Production deployments replace this by calling ``api.auth.login``. */
const DEFAULT_DEV_TOKEN = import.meta.env.VITE_GORZEN_DEV_TOKEN ?? 'dev-local-token';

/**
 * Subscriber hook for API-level errors. The global BackendStatus banner
 * attaches here so every failed request surfaces as a single visible
 * notification instead of being swallowed by individual `try/catch`es.
 */
export type ApiErrorKind = 'network' | 'unauthorized' | 'database_unavailable' | 'rate_limited' | 'http_error';
export interface ApiError {
  kind: ApiErrorKind;
  status?: number;
  path: string;
  message: string;
  hint?: string;
  at: number;
}

type ErrorListener = (err: ApiError) => void;
const errorListeners = new Set<ErrorListener>();

export function onApiError(listener: ErrorListener): () => void {
  errorListeners.add(listener);
  return () => errorListeners.delete(listener);
}

function emitError(err: ApiError): void {
  for (const listener of errorListeners) {
    try {
      listener(err);
    } catch {
      /* listener errors must not break requests */
    }
  }
}

/**
 * Read/write the auth token used for Authorization headers and the
 * telemetry WebSocket `?token=` query. In production this is the JWT
 * from `/auth/token`; in dev it's the shared secret the backend accepts
 * via ``GORZEN_DEV_WS_TOKEN`` / ``GORZEN_BRIDGE_TOKEN``.
 */
export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_STORAGE_KEY) ?? DEFAULT_DEV_TOKEN;
    } catch {
      return DEFAULT_DEV_TOKEN;
    }
  },
  set(token: string | null): void {
    try {
      if (token) localStorage.setItem(TOKEN_STORAGE_KEY, token);
      else localStorage.removeItem(TOKEN_STORAGE_KEY);
    } catch {
      /* cookies disabled; auth still works for the lifetime of the tab */
    }
  },
};

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const t = tokenStore.get();
  if (t) headers['Authorization'] = `Bearer ${t}`;
  return headers;
}

async function request<T = unknown>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...authHeaders(), ...options?.headers },
      ...options,
    });
  } catch (networkErr) {
    const message = networkErr instanceof Error ? networkErr.message : 'Network error';
    const err: ApiError = { kind: 'network', path, message, at: Date.now() };
    emitError(err);
    throw new Error(`API ${path}: ${message}`);
  }
  if (!res.ok) {
    let bodyText = '';
    let hint: string | undefined;
    try {
      const clone = res.clone();
      const ct = res.headers.get('content-type') ?? '';
      if (ct.includes('application/json')) {
        const body = await clone.json().catch(() => ({}));
        hint = (body as { hint?: string })?.hint;
        bodyText = (body as { detail?: string })?.detail ?? JSON.stringify(body);
      } else {
        bodyText = await clone.text();
      }
    } catch {
      bodyText = res.statusText;
    }
    const kind: ApiErrorKind =
      res.status === 401 || res.status === 403
        ? 'unauthorized'
        : res.status === 429
        ? 'rate_limited'
        : res.status === 503
        ? 'database_unavailable'
        : 'http_error';
    const err: ApiError = {
      kind,
      status: res.status,
      path,
      message: bodyText || `API ${res.status}`,
      hint,
      at: Date.now(),
    };
    emitError(err);
    throw new Error(`API ${res.status}: ${bodyText}`);
  }
  return res.json();
}

async function uploadForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: 'POST', body: form, headers: authHeaders() });
  if (!res.ok) {
    const bodyText = await res.text().catch(() => res.statusText);
    emitError({
      kind: res.status === 401 || res.status === 403 ? 'unauthorized' : 'http_error',
      status: res.status,
      path,
      message: bodyText,
      at: Date.now(),
    });
    throw new Error(`Upload ${res.status}: ${bodyText}`);
  }
  return res.json();
}

export const api = {
  health: {
    api: () => request<{ status: string }>('/health'),
    ready: () => request<{ status: string }>('/ready'),
  },
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
  execution: {
    upload: (connection_url: string, mavlink_items: Record<string, unknown>[], bypass_preflight = false) =>
      request<MissionUploadResponse>('/execution/upload', {
        method: 'POST',
        body: JSON.stringify({ connection_url, mavlink_items, bypass_preflight }),
      }),
    start: (connection_url = 'udp://:14540') =>
      request<{ status: string; message: string }>(
        `/execution/start?connection_url=${encodeURIComponent(connection_url)}`,
        { method: 'POST' },
      ),
    progress: (connection_url = 'udp://:14540') =>
      request<{ current: number; total: number; finished: boolean }>(
        `/execution/progress?connection_url=${encodeURIComponent(connection_url)}`,
      ),
  },
  catalog: {
    list: (subsystem_type?: string) => {
      const q = subsystem_type ? `?subsystem_type=${encodeURIComponent(subsystem_type)}` : '';
      return request<CatalogEntry[]>(`/catalog/${q}`);
    },
    /** Fetch a single entry by UUID. The previous `byType` method pointed at
     * this route with a subsystem string and always 404ed. */
    get: (entryId: string) => request<CatalogEntry>(`/catalog/${encodeURIComponent(entryId)}`),
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
    /** New (Phase 1b): per-sensor ``SYS_STATUS`` bitmask + pre-arm messages. */
    health: () => request<FcHealthSummary>('/telemetry/health'),
    /** New (Phase 3e): aggregated pre-flight readiness checklist. */
    preflight: () => request<PreflightSummary>('/telemetry/preflight'),
    paramMap: () =>
      request<{ mappings: import('../types/api').ParamMapping[]; groups: unknown[]; total: number }>(
        '/telemetry/params/map',
      ),
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
    uploadLog: (file: File) => {
      const form = new FormData();
      form.append('file', file);
      return uploadForm<LogUploadResponse & Record<string, unknown>>('/telemetry/logs/upload', form);
    },
    uploadCalibration: (file: File) => {
      const form = new FormData();
      form.append('file', file);
      return uploadForm<Record<string, unknown>>('/telemetry/logs/calibration', form);
    },
    analyzeLog: (file: File) => {
      const form = new FormData();
      form.append('file', file);
      return uploadForm<Record<string, unknown>>('/telemetry/logs/analyze', form);
    },
    listLogs: () => request<Record<string, unknown>[]>('/telemetry-logs/'),
    createCalibrationFromLog: (logId: string, twinId: string) =>
      request<Record<string, unknown>>('/telemetry/logs/create-calibration', {
        method: 'POST',
        body: JSON.stringify({ log_id: logId, twin_id: twinId }),
      }),
    /** New (Phase 3f): enumerate, download, erase the FC's on-board log store. */
    listLogsFromFc: () => request<FcLogList>('/telemetry/logs/list-from-fc'),
    downloadLogFromFc: (log_id: number, chunk_size = 90) =>
      request<FcLogDownload>('/telemetry/logs/download-from-fc', {
        method: 'POST',
        body: JSON.stringify({ log_id, chunk_size }),
      }),
    eraseFcLogs: () =>
      request<{ status: string }>('/telemetry/logs/erase-fc', { method: 'POST' }),
    syncParamsToFC: (params: Record<string, Record<string, unknown>>) =>
      request<{ synced: number; failed: number; params: Record<string, boolean> }>(
        '/telemetry/params/sync-to-fc',
        { method: 'POST', body: JSON.stringify({ params }) },
      ),
    readParamsFromFC: () =>
      request<{
        fc_param_count: number;
        twin_params: Record<string, Record<string, unknown>>;
        subsystems_affected: string[];
        raw_fc_params?: Record<string, { value: number; type: number }>;
      }>('/telemetry/params/read-from-fc', { method: 'POST' }),
    /** Accepts the new PX4 geofence shape (inclusion + exclusion polygons) or the
     * single-polygon legacy body for backward compatibility. */
    uploadGeofence: (req: GeofenceUploadRequest) =>
      request<{ success: boolean; inclusion_polygons?: number; exclusion_polygons?: number; message: string }>(
        '/telemetry/geofence/upload',
        { method: 'POST', body: JSON.stringify(req) },
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
      request<{
        imported: boolean;
        waypoint_count: number;
        estimated_distance_m: number;
        estimated_duration_s: number;
      }>('/mission-plan/import/plan', { method: 'POST', body: JSON.stringify(planData) }),
    exportQgc: () => request<Record<string, unknown>>('/mission-plan/export/qgc'),
    exportPx4: () => request<Record<string, unknown>>('/mission-plan/export/px4'),
    exportKml: async (): Promise<string> => {
      const res = await fetch(`${API_BASE}/mission-plan/export/kml`, { headers: authHeaders() });
      if (!res.ok) throw new Error(`KML export ${res.status}`);
      return res.text();
    },
    validate: (body: MissionValidateRequest) =>
      request<MissionValidateResponse>('/mission-plan/validate', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  },
  auth: {
    login: async (username: string, password: string) => {
      const form = new URLSearchParams();
      form.set('username', username);
      form.set('password', password);
      const res = await fetch(`${API_BASE}/auth/token`, {
        method: 'POST',
        body: form,
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      if (!res.ok) {
        const bodyText = await res.text().catch(() => res.statusText);
        emitError({
          kind: 'unauthorized',
          status: res.status,
          path: '/auth/token',
          message: bodyText,
          at: Date.now(),
        });
        throw new Error(`Login failed: ${res.status}`);
      }
      const body = (await res.json()) as { access_token: string; token_type: string };
      tokenStore.set(body.access_token);
      return body;
    },
    logout: () => {
      tokenStore.set(null);
    },
  },
};

/**
 * Resolve a WebSocket URL against the Vite proxy, including the
 * ``?token=`` query string expected by the backend. Always attaches a
 * token when one is configured — this mirrors the backend's new
 * "WebSocket always requires a token" contract even in dev mode.
 */
export function telemetryWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const token = tokenStore.get();
  const qs = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${protocol}//${window.location.host}${API_BASE}/telemetry/ws${qs}`;
}
