import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Trash2, Upload, Download, RotateCcw, Navigation, Crosshair, MapPin,
  Wind, Thermometer, ChevronDown, ChevronRight, Home, Shield, Camera,
  Battery, Mountain,
} from 'lucide-react';
import { CesiumGlobe } from './CesiumGlobe';
import type { GlobeWaypoint, WeatherOverlay } from './CesiumGlobe';
import { api } from '../../api/client';

interface MissionAnalysis {
  total_distance_m: number;
  total_distance_nmi: number;
  estimated_duration_s: number;
  estimated_duration_min: number;
  max_altitude_m: number;
  min_altitude_m: number;
  waypoint_count: number;
  avg_speed_ms: number;
  leg_distances_m: number[];
}

interface TerrainPoint { latitude: number; longitude: number; elevation_m: number }

const CAMERA_ACTIONS = ['none', 'photo', 'start_video', 'stop_video'] as const;

export function MissionPlanner() {
  const [waypoints, setWaypoints] = useState<GlobeWaypoint[]>([]);
  const [analysis, setAnalysis] = useState<MissionAnalysis | null>(null);
  const [dronePosition, setDronePosition] = useState<{ lat: number; lon: number; alt: number } | null>(null);
  const [homePosition, setHomePosition] = useState<{ lat: number; lon: number } | null>(null);
  const [defaultAlt, setDefaultAlt] = useState(100);
  const [defaultSpeed, setDefaultSpeed] = useState(15);
  const [status, setStatus] = useState<string | null>(null);
  const [weather, setWeather] = useState<WeatherOverlay | null>(null);
  const [editingWp, setEditingWp] = useState<number | null>(null);
  const [geofenceRadius, setGeofenceRadius] = useState(0);
  const [terrainProfile, setTerrainProfile] = useState<TerrainPoint[] | null>(null);
  const [terrainLoading, setTerrainLoading] = useState(false);
  const flyToMeRef = useRef<(() => void) | null>(null);

  // --- Data fetching effects (unchanged) ---

  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => setHomePosition({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
        () => setHomePosition({ lat: 41.905, lon: -84.632 }),
      );
    }
  }, []);

  useEffect(() => {
    if (!homePosition) return;
    let active = true;
    const fetchWeather = async () => {
      try {
        const data = await api.environment.weather(homePosition.lat, homePosition.lon);
        if (!active) return;
        const surfaceWind = data.wind_layers?.[0];
        setWeather({
          temperature_c: data.temperature_c ?? 0,
          wind_speed_ms: surfaceWind?.speed_ms ?? 0,
          wind_direction_deg: surfaceWind?.direction_deg ?? 0,
          pressure_hpa: data.pressure_hpa ?? 1013,
          density_altitude_ft: data.density_altitude_ft ?? 0,
          flight_category: data.flight_category ?? 'VFR',
          humidity_pct: data.humidity_pct,
          visibility_km: data.visibility_m != null ? data.visibility_m / 1000 : undefined,
        });
      } catch { /* not critical */ }
    };
    fetchWeather();
    const interval = setInterval(fetchWeather, 120000);
    return () => { active = false; clearInterval(interval); };
  }, [homePosition]);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const data = await api.telemetry.status();
        if (data.connected) {
          const snap = await api.telemetry.snapshot();
          if (snap.position && active) {
            setDronePosition({
              lat: snap.position.latitude_deg,
              lon: snap.position.longitude_deg,
              alt: snap.position.relative_altitude_m ?? 0,
            });
          }
        }
      } catch { /* not connected */ }
    };
    const interval = setInterval(poll, 2000);
    poll();
    return () => { active = false; clearInterval(interval); };
  }, []);

  useEffect(() => {
    api.missionPlan.getWaypoints().then((data) => {
      if (data.waypoints?.length > 0) {
        setWaypoints(data.waypoints);
        setAnalysis(data.analysis);
      }
    }).catch(() => {});
  }, []);

  // --- Terrain profile fetch ---

  const fetchTerrainProfile = useCallback(async (wps: GlobeWaypoint[]) => {
    if (wps.length < 2) { setTerrainProfile(null); return; }
    setTerrainLoading(true);
    try {
      // Interpolate ~30 points along the path
      const points: number[][] = [];
      for (let i = 0; i < wps.length - 1; i++) {
        const steps = Math.max(3, Math.ceil(30 / (wps.length - 1)));
        for (let s = 0; s <= steps; s++) {
          const t = s / steps;
          points.push([
            wps[i].latitude_deg + t * (wps[i + 1].latitude_deg - wps[i].latitude_deg),
            wps[i].longitude_deg + t * (wps[i + 1].longitude_deg - wps[i].longitude_deg),
          ]);
        }
      }
      const res = await api.environment.terrainProfile(points);
      setTerrainProfile(res.points ?? []);
    } catch {
      setTerrainProfile(null);
    }
    setTerrainLoading(false);
  }, []);

  // --- Waypoint operations ---

  const syncToServer = useCallback(async (wps: GlobeWaypoint[]) => {
    try {
      const res = await api.missionPlan.setWaypoints(
        wps.map((wp) => ({
          latitude_deg: wp.latitude_deg,
          longitude_deg: wp.longitude_deg,
          altitude_m: wp.altitude_m,
          speed_ms: wp.speed_ms ?? defaultSpeed,
          loiter_time_s: wp.loiter_time_s ?? 0,
          camera_action: wp.camera_action ?? 'none',
        }))
      );
      setAnalysis(res.analysis);
    } catch { /* silent */ }
    fetchTerrainProfile(wps);
  }, [defaultSpeed, fetchTerrainProfile]);

  const handleAddWaypoint = useCallback((lat: number, lon: number, _alt: number) => {
    const wp: GlobeWaypoint = {
      latitude_deg: lat, longitude_deg: lon, altitude_m: defaultAlt,
      order: waypoints.length, speed_ms: defaultSpeed, loiter_time_s: 0, camera_action: 'none',
    };
    const updated = [...waypoints, wp];
    setWaypoints(updated);
    syncToServer(updated);
  }, [waypoints, defaultAlt, defaultSpeed, syncToServer]);

  const handleRemoveWaypoint = useCallback((index: number) => {
    const updated = waypoints.filter((_, i) => i !== index).map((wp, i) => ({ ...wp, order: i }));
    setWaypoints(updated);
    setEditingWp(null);
    syncToServer(updated);
  }, [waypoints, syncToServer]);

  const handleMoveWaypoint = useCallback((index: number, lat: number, lon: number) => {
    const updated = waypoints.map((wp, i) => i === index ? { ...wp, latitude_deg: lat, longitude_deg: lon } : wp);
    setWaypoints(updated);
    syncToServer(updated);
  }, [waypoints, syncToServer]);

  const handleUpdateWaypoint = useCallback((index: number, field: string, value: number | string) => {
    const updated = waypoints.map((wp, i) => i === index ? { ...wp, [field]: value } : wp);
    setWaypoints(updated);
    syncToServer(updated);
  }, [waypoints, syncToServer]);

  const handleClear = useCallback(() => {
    setWaypoints([]); setAnalysis(null); setTerrainProfile(null); setEditingWp(null);
    api.missionPlan.clearWaypoints().catch(() => {});
  }, []);

  const handleAddRTL = useCallback(() => {
    if (!homePosition || waypoints.length === 0) return;
    const rtl: GlobeWaypoint = {
      latitude_deg: homePosition.lat, longitude_deg: homePosition.lon,
      altitude_m: defaultAlt, order: waypoints.length,
      speed_ms: defaultSpeed, loiter_time_s: 0, camera_action: 'none',
    };
    const updated = [...waypoints, rtl];
    setWaypoints(updated);
    syncToServer(updated);
  }, [waypoints, homePosition, defaultAlt, defaultSpeed, syncToServer]);

  const handleUploadToDrone = useCallback(async () => {
    setStatus('Uploading...');
    try {
      const res = await api.missionPlan.uploadToDrone();
      setStatus(res.success ? `Uploaded ${res.waypoints_uploaded} waypoints` : `Failed: ${res.error}`);
    } catch (e: any) { setStatus(`Upload error: ${e.message}`); }
    setTimeout(() => setStatus(null), 4000);
  }, []);

  const handleDownloadFromDrone = useCallback(async () => {
    setStatus('Downloading...');
    try {
      const res = await api.missionPlan.downloadFromDrone();
      if (res.success) {
        setStatus(`Downloaded ${res.waypoints_downloaded} waypoints`);
        const data = await api.missionPlan.getWaypoints();
        setWaypoints(data.waypoints);
        setAnalysis(data.analysis);
        fetchTerrainProfile(data.waypoints);
      } else { setStatus(`Failed: ${res.error}`); }
    } catch (e: any) { setStatus(`Download error: ${e.message}`); }
    setTimeout(() => setStatus(null), 4000);
  }, [fetchTerrainProfile]);

  // --- Terrain profile SVG ---
  const renderTerrainProfile = () => {
    if (!terrainProfile || terrainProfile.length < 2 || waypoints.length < 2) return null;
    const elevations = terrainProfile.map((p) => p.elevation_m);
    const minE = Math.min(...elevations);
    const maxFlight = Math.max(...waypoints.map((w) => w.altitude_m));
    const maxE = Math.max(...elevations, maxFlight + 50);
    const range = maxE - minE || 1;
    const w = 240;
    const h = 60;

    // Terrain polygon
    const pts = elevations.map((e, i) => {
      const x = (i / (elevations.length - 1)) * w;
      const y = h - ((e - minE) / range) * h;
      return `${x},${y}`;
    });
    const terrainPath = `M0,${h} ${pts.map((p, i) => (i === 0 ? `L${p}` : `L${p}`)).join(' ')} L${w},${h} Z`;

    // Flight altitude line
    const flightPts = waypoints.map((wp, i) => {
      const x = (i / (waypoints.length - 1)) * w;
      const y = h - ((wp.altitude_m + (elevations[0] ?? 0) - minE) / range) * h;
      return `${x},${Math.max(0, y)}`;
    }).join(' ');

    // Min ground clearance
    const clearances = waypoints.map((wp, i) => {
      const idx = Math.round((i / (waypoints.length - 1)) * (elevations.length - 1));
      return wp.altitude_m + (elevations[0] ?? 0) - (elevations[idx] ?? 0);
    });
    const minClearance = Math.min(...clearances);

    return (
      <div className="p-4 border-t border-white/[0.06]">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-2 flex items-center gap-1.5">
          <Mountain size={11} className="text-emerald-400" />
          Terrain Profile
        </h3>
        <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height: 60 }}>
          <path d={terrainPath} fill="rgba(16,185,129,0.15)" stroke="rgba(16,185,129,0.4)" strokeWidth="1" />
          <polyline points={flightPts} fill="none" stroke="rgba(59,130,246,0.8)" strokeWidth="1.5" strokeDasharray="4,2" />
        </svg>
        <div className="flex justify-between mt-1 text-[9px] font-mono text-white/30">
          <span>{minE.toFixed(0)}m</span>
          <span className={minClearance < 30 ? 'text-red-400' : minClearance < 100 ? 'text-amber-400' : 'text-emerald-400'}>
            Min clearance: {minClearance.toFixed(0)}m AGL
          </span>
          <span>{maxE.toFixed(0)}m</span>
        </div>
      </div>
    );
  };

  return (
    <div className="flex h-full w-full">
      {/* Globe */}
      <div className="flex-1 relative">
        <CesiumGlobe
          waypoints={waypoints}
          dronePosition={dronePosition}
          operatorPosition={homePosition}
          weather={weather}
          onAddWaypoint={handleAddWaypoint}
          onRemoveWaypoint={handleRemoveWaypoint}
          onMoveWaypoint={handleMoveWaypoint}
          onFlyTo={(fn) => { flyToMeRef.current = fn; }}
          homePosition={homePosition}
          geofenceRadius={geofenceRadius}
        />

        {/* Overlay controls */}
        <div className="absolute top-3 left-3 flex gap-2 flex-wrap">
          <div className="glass-panel p-2 flex gap-1.5 flex-wrap">
            <button onClick={() => flyToMeRef.current?.()} className="glass-button px-2.5 py-1.5 text-[11px] flex items-center gap-1.5" title="Fly to my location">
              <Crosshair size={12} /> My Loc
            </button>
            <button onClick={handleAddRTL} className="glass-button px-2.5 py-1.5 text-[11px] flex items-center gap-1.5" title="Add return-to-launch waypoint"
              disabled={!homePosition || waypoints.length === 0}>
              <Home size={12} /> RTL
            </button>
            <button onClick={handleClear} className="glass-button px-2.5 py-1.5 text-[11px] flex items-center gap-1.5" title="Clear mission">
              <RotateCcw size={12} /> Clear
            </button>
            <button onClick={handleUploadToDrone} className="glass-button px-2.5 py-1.5 text-[11px] flex items-center gap-1.5" title="Upload to drone">
              <Upload size={12} /> Upload
            </button>
            <button onClick={handleDownloadFromDrone} className="glass-button px-2.5 py-1.5 text-[11px] flex items-center gap-1.5" title="Download from drone">
              <Download size={12} /> Download
            </button>
          </div>
        </div>

        {/* Instructions overlay */}
        <div className="absolute bottom-3 left-3 glass-panel p-2 text-[10px] text-white/50 max-w-xs">
          <span className="text-gorzen-400 font-medium">Double-click</span> add &middot;
          <span className="text-gorzen-400 font-medium"> Drag</span> move &middot;
          <span className="text-gorzen-400 font-medium"> Right-click</span> remove
        </div>

        {/* Weather overlay */}
        {weather && (
          <div className="absolute bottom-3 right-3 glass-panel p-3 min-w-[180px]">
            <div className="flex items-center gap-1.5 mb-2">
              <Thermometer size={11} className="text-sky-400" />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-white/40">Weather</span>
              <span className="ml-auto text-[9px] font-bold px-1.5 py-0.5 rounded"
                style={{
                  color: weather.flight_category === 'VFR' ? '#10b981' : weather.flight_category === 'MVFR' ? '#3b82f6' : weather.flight_category === 'IFR' ? '#f59e0b' : '#ef4444',
                  backgroundColor: weather.flight_category === 'VFR' ? 'rgba(16,185,129,0.15)' : weather.flight_category === 'MVFR' ? 'rgba(59,130,246,0.15)' : weather.flight_category === 'IFR' ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)',
                }}>
                {weather.flight_category}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] font-mono">
              <span className="text-white/35">Temp</span>
              <span className="text-white/70 text-right">{weather.temperature_c.toFixed(1)}&deg;C</span>
              <span className="text-white/35">Wind</span>
              <span className="text-white/70 text-right flex items-center justify-end gap-1">
                <Wind size={9} className="text-sky-400/70" />
                {weather.wind_speed_ms.toFixed(1)} m/s
              </span>
              <span className="text-white/35">Dir</span>
              <span className="text-white/70 text-right">{weather.wind_direction_deg.toFixed(0)}&deg;</span>
              <span className="text-white/35">Pressure</span>
              <span className="text-white/70 text-right">{weather.pressure_hpa.toFixed(0)} hPa</span>
              <span className="text-white/35">DA</span>
              <span className="text-white/70 text-right">{weather.density_altitude_ft.toFixed(0)} ft</span>
              {weather.humidity_pct != null && (
                <>
                  <span className="text-white/35">Humidity</span>
                  <span className="text-white/70 text-right">{weather.humidity_pct.toFixed(0)}%</span>
                </>
              )}
            </div>
          </div>
        )}

        {/* Status toast */}
        {status && (
          <div className="absolute top-3 right-3 glass-panel p-3 text-xs text-white/80 animate-pulse">
            {status}
          </div>
        )}
      </div>

      {/* Right sidebar */}
      <div className="w-72 flex-shrink-0 overflow-y-auto border-l border-white/[0.06] bg-surface-dark/30">
        {/* Defaults + Geofence */}
        <div className="p-4 border-b border-white/[0.06]">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">Defaults</h3>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="text-[10px] text-white/40 block mb-1">Alt (m)</label>
              <input type="number" value={defaultAlt} onChange={(e) => setDefaultAlt(Number(e.target.value))}
                className="glass-input w-full text-xs px-2 py-1.5" />
            </div>
            <div>
              <label className="text-[10px] text-white/40 block mb-1">Speed</label>
              <input type="number" value={defaultSpeed} onChange={(e) => setDefaultSpeed(Number(e.target.value))}
                className="glass-input w-full text-xs px-2 py-1.5" />
            </div>
            <div>
              <label className="text-[10px] text-white/40 block mb-1 flex items-center gap-1">
                <Shield size={9} className="text-amber-400" /> Fence
              </label>
              <input type="number" value={geofenceRadius} onChange={(e) => setGeofenceRadius(Number(e.target.value))}
                className="glass-input w-full text-xs px-2 py-1.5" placeholder="0" />
            </div>
          </div>
        </div>

        {/* GPS Location */}
        {homePosition && (
          <div className="p-4 border-b border-white/[0.06]">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-2 flex items-center gap-1.5">
              <MapPin size={11} className="text-cyan-400" /> Your Location
            </h3>
            <div className="space-y-1 font-mono text-[10px] text-white/50">
              <div className="flex justify-between">
                <span className="text-white/30">Lat</span><span>{homePosition.lat.toFixed(6)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-white/30">Lon</span><span>{homePosition.lon.toFixed(6)}</span>
              </div>
            </div>
            <div className="mt-1.5 flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              <span className="text-[9px] text-cyan-400/60">GPS active</span>
            </div>
          </div>
        )}

        {/* Waypoint list with inline editing */}
        <div className="p-4 border-b border-white/[0.06]">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
            Waypoints ({waypoints.length})
          </h3>
          {waypoints.length === 0 ? (
            <div className="text-[11px] text-white/25 text-center py-6">
              Double-click the globe to add waypoints
            </div>
          ) : (
            <div className="space-y-0.5 max-h-80 overflow-y-auto">
              {waypoints.map((wp, i) => {
                const isEditing = editingWp === i;
                const isFirst = i === 0;
                const isLast = i === waypoints.length - 1 && waypoints.length > 1;
                return (
                  <div key={i}>
                    <div
                      className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-white/[0.04] group transition-colors cursor-pointer"
                      onClick={() => setEditingWp(isEditing ? null : i)}
                    >
                      <span className="w-4 text-[10px] font-mono" style={{
                        color: isFirst ? '#10b981' : isLast ? '#ef4444' : 'rgba(255,255,255,0.3)',
                      }}>{wp.order}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-[10px] font-mono text-white/60 truncate">
                          {wp.latitude_deg.toFixed(5)}, {wp.longitude_deg.toFixed(5)}
                        </div>
                        <div className="text-[9px] text-white/30 flex items-center gap-1.5">
                          <span>{wp.altitude_m}m</span>
                          <span>&middot;</span>
                          <span>{wp.speed_ms ?? defaultSpeed}m/s</span>
                          {wp.camera_action && wp.camera_action !== 'none' && (
                            <Camera size={8} className="text-gorzen-400" />
                          )}
                          {(wp.loiter_time_s ?? 0) > 0 && (
                            <span className="text-gorzen-400">{wp.loiter_time_s}s</span>
                          )}
                        </div>
                      </div>
                      {isEditing ? <ChevronDown size={11} className="text-white/30" /> : <ChevronRight size={11} className="text-white/15" />}
                      <button onClick={(e) => { e.stopPropagation(); handleRemoveWaypoint(i); }}
                        className="opacity-0 group-hover:opacity-100 text-red-400/60 hover:text-red-400 transition-all p-1">
                        <Trash2 size={11} />
                      </button>
                    </div>

                    {/* Inline waypoint editor */}
                    {isEditing && (
                      <div className="px-3 py-2 ml-4 mr-1 mb-1 rounded-lg bg-white/[0.03] border border-white/[0.06] space-y-2">
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="text-[9px] text-white/30 block mb-0.5">Altitude (m)</label>
                            <input type="number" value={wp.altitude_m}
                              onChange={(e) => handleUpdateWaypoint(i, 'altitude_m', Number(e.target.value))}
                              className="glass-input w-full text-[10px] px-2 py-1" />
                          </div>
                          <div>
                            <label className="text-[9px] text-white/30 block mb-0.5">Speed (m/s)</label>
                            <input type="number" value={wp.speed_ms ?? defaultSpeed}
                              onChange={(e) => handleUpdateWaypoint(i, 'speed_ms', Number(e.target.value))}
                              className="glass-input w-full text-[10px] px-2 py-1" />
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="text-[9px] text-white/30 block mb-0.5">Loiter (s)</label>
                            <input type="number" value={wp.loiter_time_s ?? 0}
                              onChange={(e) => handleUpdateWaypoint(i, 'loiter_time_s', Number(e.target.value))}
                              className="glass-input w-full text-[10px] px-2 py-1" />
                          </div>
                          <div>
                            <label className="text-[9px] text-white/30 block mb-0.5">Camera</label>
                            <select value={wp.camera_action ?? 'none'}
                              onChange={(e) => handleUpdateWaypoint(i, 'camera_action', e.target.value)}
                              className="glass-input w-full text-[10px] px-2 py-1 bg-transparent">
                              {CAMERA_ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
                            </select>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Terrain profile */}
        {terrainLoading && (
          <div className="p-4 border-t border-white/[0.06] text-[10px] text-white/30 text-center">
            Loading terrain...
          </div>
        )}
        {!terrainLoading && renderTerrainProfile()}

        {/* Mission analysis */}
        {analysis && analysis.waypoint_count > 0 && (
          <div className="p-4 border-t border-white/[0.06]">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
              Mission Analysis
            </h3>
            <div className="space-y-2">
              {[
                { label: 'Distance', value: `${(analysis.total_distance_m / 1000).toFixed(2)} km`, sub: `${analysis.total_distance_nmi} nmi` },
                { label: 'Duration', value: `${analysis.estimated_duration_min} min`, sub: `${analysis.estimated_duration_s.toFixed(0)}s` },
                { label: 'Waypoints', value: `${analysis.waypoint_count}`, sub: `${analysis.leg_distances_m.length} legs` },
                { label: 'Alt Range', value: `${analysis.min_altitude_m} - ${analysis.max_altitude_m} m`, sub: '' },
                { label: 'Avg Speed', value: `${analysis.avg_speed_ms} m/s`, sub: `${(analysis.avg_speed_ms * 1.944).toFixed(1)} kts` },
              ].map(({ label, value, sub }) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-[10px] text-white/40">{label}</span>
                  <div className="text-right">
                    <span className="text-xs font-mono text-gorzen-400">{value}</span>
                    {sub && <span className="text-[9px] text-white/25 ml-1.5">{sub}</span>}
                  </div>
                </div>
              ))}
            </div>

            {/* Estimated battery usage (simple model) */}
            {analysis.estimated_duration_min > 0 && (
              <div className="mt-3 pt-3 border-t border-white/[0.06]">
                <h4 className="text-[10px] font-semibold uppercase tracking-wider text-white/30 mb-2 flex items-center gap-1.5">
                  <Battery size={9} className="text-amber-400" /> Battery Estimate
                </h4>
                {(() => {
                  // Simple battery model: assume 25 min total endurance
                  const enduranceMin = 25;
                  const usagePct = Math.min(100, (analysis.estimated_duration_min / enduranceMin) * 100);
                  const remainPct = 100 - usagePct;
                  const isOk = remainPct >= 30;
                  const isWarn = remainPct >= 15 && remainPct < 30;
                  return (
                    <div>
                      <div className="flex justify-between text-[10px] font-mono mb-1">
                        <span className="text-white/40">Usage</span>
                        <span className={isOk ? 'text-emerald-400' : isWarn ? 'text-amber-400' : 'text-red-400'}>
                          {usagePct.toFixed(0)}% ({analysis.estimated_duration_min} / {enduranceMin} min)
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                        <div className="h-full rounded-full transition-all"
                          style={{
                            width: `${usagePct}%`,
                            backgroundColor: isOk ? '#10b981' : isWarn ? '#f59e0b' : '#ef4444',
                          }} />
                      </div>
                      <div className="text-[9px] mt-1" style={{ color: isOk ? '#10b981' : isWarn ? '#f59e0b' : '#ef4444' }}>
                        {remainPct.toFixed(0)}% remaining{!isOk && !isWarn ? ' — INSUFFICIENT' : isWarn ? ' — LOW' : ''}
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Leg breakdown */}
            {analysis.leg_distances_m.length > 0 && (
              <div className="mt-3 pt-3 border-t border-white/[0.06]">
                <h4 className="text-[10px] font-semibold uppercase tracking-wider text-white/30 mb-2">Leg Distances</h4>
                <div className="space-y-1">
                  {analysis.leg_distances_m.map((d, i) => {
                    const maxDist = Math.max(...analysis.leg_distances_m);
                    const pct = maxDist > 0 ? (d / maxDist) * 100 : 0;
                    return (
                      <div key={i} className="flex items-center gap-2">
                        <span className="text-[9px] font-mono text-white/25 w-8">{i}&rarr;{i + 1}</span>
                        <div className="flex-1 h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
                          <div className="h-full rounded-full bg-gorzen-500/40" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-[9px] font-mono text-white/35 w-12 text-right">
                          {d < 1000 ? `${d.toFixed(0)}m` : `${(d / 1000).toFixed(2)}km`}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Drone status */}
        {dronePosition && (
          <div className="p-4 border-t border-white/[0.06]">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-2 flex items-center gap-1.5">
              <Navigation size={11} className="text-amber-400" /> Live Drone
            </h3>
            <div className="space-y-1 font-mono text-[10px] text-white/50">
              <div>Lat: {dronePosition.lat.toFixed(6)}</div>
              <div>Lon: {dronePosition.lon.toFixed(6)}</div>
              <div>Alt: {dronePosition.alt.toFixed(1)} m</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
