import React, { useState, useEffect, useCallback } from 'react';
import { GlassPanel } from '../layout/GlassPanel';
import { chartStyles } from '../../theme/chartStyles';
import { colors } from '../../theme/tokens';
import { api } from '../../api/client';

interface WindLayer {
  height_m: number;
  speed_ms: number;
  direction_deg: number;
  gusts_ms: number;
}

interface WeatherData {
  temperature_c: number;
  pressure_hpa: number;
  humidity_pct: number;
  cloud_cover_pct: number;
  visibility_m: number;
  precipitation_mm: number;
  density_altitude_ft: number;
  air_density_kgm3: number;
  flight_category: string;
  conditions_summary: string;
  timestamp: string;
  wind_layers: WindLayer[];
}

interface SolarData {
  elevation_deg: number;
  azimuth_deg: number;
  zenith_deg: number;
  sunrise_hour: number;
  sunset_hour: number;
  day_length_hr: number;
  ghi_w_m2: number;
  dni_w_m2: number;
  dhi_w_m2: number;
  illuminance_lux: number;
  solar_noon_utc: string;
  is_daytime: boolean;
}

export interface EnvironmentSnapshot {
  temperature_c: number;
  pressure_hpa: number;
  wind_speed_ms: number;
  wind_direction_deg: number;
  density_altitude_ft: number;
  ambient_light_lux: number;
  air_density_kgm3: number;
}

interface EnvironmentIntelProps {
  onEnvironmentData?: (snapshot: EnvironmentSnapshot) => void;
  sharedLocation?: { lat: number; lon: number } | null;
}

const FLIGHT_CAT_COLORS: Record<string, string> = {
  VFR: colors.status.success,
  MVFR: colors.status.info,
  IFR: colors.status.warning,
  LIFR: colors.status.danger,
};

function decimalHourToTime(h: number): string {
  const hours = Math.floor(((h % 24) + 24) % 24);
  const mins = Math.floor((h % 1) * 60);
  return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}`;
}

function WindCompass({ layers }: { layers: WindLayer[] }) {
  const size = 160;
  const cx = size / 2;
  const cy = size / 2;
  const outerR = 62;
  const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'] as const;

  const maxSpeed = Math.max(20, ...layers.map(l => l.speed_ms));

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="select-none">
      {/* Concentric range rings */}
      {[0.33, 0.66, 1.0].map(f => (
        <circle key={f} cx={cx} cy={cy} r={outerR * f} fill="none"
          stroke="rgba(255,255,255,0.05)" strokeWidth={0.5} />
      ))}

      {/* Cardinal/intercardinal labels */}
      {dirs.map((d, i) => {
        const a = ((i * 45 - 90) * Math.PI) / 180;
        const isPrimary = i % 2 === 0;
        return (
          <text key={d}
            x={cx + Math.cos(a) * (outerR + 9)}
            y={cy + Math.sin(a) * (outerR + 9)}
            textAnchor="middle" dominantBaseline="central"
            className={`font-mono ${isPrimary ? 'fill-white/35 text-[8px] font-medium' : 'fill-white/15 text-[7px]'}`}
          >{d}</text>
        );
      })}

      {/* Wind vectors — one per altitude layer, progressively lighter */}
      {layers.map((layer, i) => {
        const frac = layer.speed_ms / maxSpeed;
        const len = frac * outerR;
        const angle = ((layer.direction_deg - 90) * Math.PI) / 180;
        const ex = cx + Math.cos(angle) * len;
        const ey = cy + Math.sin(angle) * len;
        const ah = 5;
        const a1x = ex - Math.cos(angle - 0.4) * ah;
        const a1y = ey - Math.sin(angle - 0.4) * ah;
        const a2x = ex - Math.cos(angle + 0.4) * ah;
        const a2y = ey - Math.sin(angle + 0.4) * ah;
        const opacity = 1 - i * 0.2;
        const strokeW = 2.5 - i * 0.4;
        const hue = 270 - i * 15;

        return (
          <g key={layer.height_m} opacity={opacity}>
            <line x1={cx} y1={cy} x2={ex} y2={ey}
              stroke={`hsl(${hue}, 60%, 75%)`} strokeWidth={strokeW} strokeLinecap="round" />
            <polygon points={`${ex},${ey} ${a1x},${a1y} ${a2x},${a2y}`}
              fill={`hsl(${hue}, 60%, 75%)`} />
          </g>
        );
      })}

      {/* Center dot */}
      <circle cx={cx} cy={cy} r={2} fill="rgba(255,255,255,0.3)" />
    </svg>
  );
}

function WindTable({ layers }: { layers: WindLayer[] }) {
  const maxSpeed = Math.max(25, ...layers.map(l => Math.max(l.speed_ms, l.gusts_ms)));

  return (
    <div className="space-y-1">
      {layers.map(layer => {
        const pct = (layer.speed_ms / maxSpeed) * 100;
        const gustPct = (layer.gusts_ms / maxSpeed) * 100;
        const gustDelta = layer.gusts_ms - layer.speed_ms;
        return (
          <div key={layer.height_m} className="flex items-center gap-2">
            <span className="text-[10px] text-white/35 font-mono w-12 text-right shrink-0">
              {layer.height_m}m
            </span>
            <div className="flex-1 h-2.5 rounded-full bg-white/[0.03] relative overflow-hidden">
              {gustDelta > 0.5 && (
                <div className="absolute inset-y-0 left-0 rounded-full bg-white/[0.08]"
                  style={{ width: `${gustPct}%` }} />
              )}
              <div className="absolute inset-y-0 left-0 rounded-full bg-white/30"
                style={{ width: `${pct}%` }} />
            </div>
            <span className="text-[10px] text-white/70 font-mono w-16 shrink-0 text-right tabular-nums">
              {layer.speed_ms.toFixed(1)}
              {gustDelta > 0.5 && (
                <span className="text-white/30"> G{layer.gusts_ms.toFixed(0)}</span>
              )}
            </span>
            <span className="text-[10px] text-white/30 font-mono w-8 shrink-0 text-right">
              {layer.direction_deg.toFixed(0)}°
            </span>
          </div>
        );
      })}
    </div>
  );
}

function SolarArc({ data }: { data: SolarData }) {
  const w = 280;
  const h = 100;
  const pad = 24;
  const horizY = h - 16;
  const arcH = horizY - 12;

  const now = new Date();
  const hourFrac = now.getUTCHours() + now.getUTCMinutes() / 60;
  const daySpan = data.sunset_hour - data.sunrise_hour;
  const dayFrac = daySpan > 0
    ? Math.max(0, Math.min(1, (hourFrac - data.sunrise_hour) / daySpan))
    : 0;

  const sunAngle = dayFrac * Math.PI;
  const sunX = pad + (1 - Math.cos(sunAngle)) * (w - pad * 2) / 2;
  const sunY = horizY - Math.sin(sunAngle) * arcH;

  const arcPath = `M ${pad} ${horizY} Q ${w / 2} ${horizY - arcH * 1.4} ${w - pad} ${horizY}`;

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="select-none">
      {/* Horizon line */}
      <line x1={pad} y1={horizY} x2={w - pad} y2={horizY}
        stroke="rgba(255,255,255,0.06)" strokeWidth={1} />

      {/* Twilight zone (below horizon, subtle) */}
      <rect x={pad} y={horizY} width={w - pad * 2} height={6}
        fill="rgba(99,102,241,0.04)" rx={1} />

      {/* Arc path */}
      <path d={arcPath} fill="none" stroke="rgba(255,255,255,0.06)"
        strokeWidth={1} strokeDasharray="4,4" />

      {/* Traversed portion of the arc (golden) */}
      {data.is_daytime && dayFrac > 0.01 && (
        <path d={arcPath} fill="none" stroke="rgba(251,191,36,0.15)"
          strokeWidth={2} strokeDasharray={`${dayFrac * 300},1000`} />
      )}

      {/* Sun position */}
      {data.is_daytime && (
        <>
          <circle cx={sunX} cy={sunY} r={14} fill="rgba(251,191,36,0.08)" />
          <circle cx={sunX} cy={sunY} r={8} fill="rgba(251,191,36,0.15)" />
          <circle cx={sunX} cy={sunY} r={4} fill="#fbbf24" />
        </>
      )}

      {/* Sunrise / sunset labels */}
      <text x={pad} y={h - 1} className="fill-white/30 text-[9px] font-mono">
        {decimalHourToTime(data.sunrise_hour)}
      </text>
      <text x={w - pad} y={h - 1} textAnchor="end" className="fill-white/30 text-[9px] font-mono">
        {decimalHourToTime(data.sunset_hour)}
      </text>

      {/* Elevation readout at sun position */}
      {data.is_daytime && (
        <text x={sunX} y={sunY - 18} textAnchor="middle"
          className="fill-amber-300/60 text-[9px] font-mono font-medium">
          {data.elevation_deg.toFixed(0)}°
        </text>
      )}
    </svg>
  );
}

function Stat({ label, value, unit, highlight }: {
  label: string; value: string | number; unit?: string; highlight?: boolean;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] uppercase tracking-wider text-white/30 mb-0.5">{label}</span>
      <span className={`text-sm font-mono tabular-nums ${highlight ? 'text-white font-bold' : 'text-white/80'}`}>
        {value}
        {unit && <span className="text-[9px] text-white/30 ml-0.5">{unit}</span>}
      </span>
    </div>
  );
}

export function EnvironmentIntel({ onEnvironmentData, sharedLocation }: EnvironmentIntelProps) {
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [solar, setSolar] = useState<SolarData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lat, setLat] = useState(35.0);
  const [lon, setLon] = useState(-106.6);
  const [geoStatus, setGeoStatus] = useState<'idle' | 'locating' | 'success' | 'denied'>('idle');
  const [usedSharedGeo, setUsedSharedGeo] = useState(false);

  const fetchData = useCallback(async (fetchLat: number, fetchLon: number) => {
    setLoading(true);
    setError(null);
    try {
      const [w, s] = await Promise.all([
        api.environment.weather(fetchLat, fetchLon),
        api.environment.solar(fetchLat, fetchLon),
      ]);
      setWeather(w);
      setSolar(s);

      if (onEnvironmentData) {
        const surfaceWind = w.wind_layers?.[0];
        onEnvironmentData({
          temperature_c: w.temperature_c,
          pressure_hpa: w.pressure_hpa,
          wind_speed_ms: surfaceWind?.speed_ms ?? 0,
          wind_direction_deg: surfaceWind?.direction_deg ?? 0,
          density_altitude_ft: w.density_altitude_ft,
          ambient_light_lux: s.illuminance_lux,
          air_density_kgm3: w.air_density_kgm3,
        });
      }
    } catch (e: any) {
      setError(e.message || 'Failed to fetch environment data');
    } finally {
      setLoading(false);
    }
  }, [onEnvironmentData]);

  const requestGeolocation = useCallback(() => {
    if (!navigator.geolocation) { setGeoStatus('denied'); return; }
    setGeoStatus('locating');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const newLat = Math.round(pos.coords.latitude * 1000) / 1000;
        const newLon = Math.round(pos.coords.longitude * 1000) / 1000;
        setLat(newLat);
        setLon(newLon);
        setGeoStatus('success');
        fetchData(newLat, newLon);
      },
      () => { setGeoStatus('denied'); fetchData(lat, lon); },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }, [fetchData, lat, lon]);

  useEffect(() => {
    if (sharedLocation && !usedSharedGeo) {
      const newLat = Math.round(sharedLocation.lat * 1000) / 1000;
      const newLon = Math.round(sharedLocation.lon * 1000) / 1000;
      setLat(newLat);
      setLon(newLon);
      setGeoStatus('success');
      setUsedSharedGeo(true);
      fetchData(newLat, newLon);
    }
  }, [sharedLocation, usedSharedGeo, fetchData]);

  useEffect(() => {
    if (!sharedLocation) requestGeolocation();
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="h-full overflow-y-auto space-y-3 p-3">
      {/* Location header */}
      <GlassPanel padding="p-3">
        <div className="flex items-center justify-between mb-2.5">
          <h2 className={chartStyles.title}>Environment Intelligence</h2>
          <div className="flex items-center gap-1.5">
            <button onClick={requestGeolocation} disabled={geoStatus === 'locating'}
              className="glass-button text-[10px] py-1 px-2.5 disabled:opacity-50">
              {geoStatus === 'locating' ? '...' : 'GPS'}
            </button>
            <button onClick={() => fetchData(lat, lon)} disabled={loading}
              className="glass-button text-[10px] py-1 px-2.5 disabled:opacity-50">
              {loading ? '...' : 'Refresh'}
            </button>
          </div>
        </div>
        <div className="flex gap-2">
          <div className="flex-1">
            <label htmlFor="env-lat" className="text-[9px] text-white/30 block mb-0.5">Lat</label>
            <input id="env-lat" type="number" value={lat} onChange={e => setLat(+e.target.value)} step={0.1}
              className="glass-input text-xs" />
          </div>
          <div className="flex-1">
            <label htmlFor="env-lon" className="text-[9px] text-white/30 block mb-0.5">Lon</label>
            <input id="env-lon" type="number" value={lon} onChange={e => setLon(+e.target.value)} step={0.1}
              className="glass-input text-xs" />
          </div>
        </div>
        {geoStatus === 'success' && (
          <div className="mt-1.5 text-[9px] text-gorzen-400 flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-gorzen-400 animate-pulse" />
            Live GPS
          </div>
        )}
        {error && <div className="mt-1.5 text-[10px] text-red-400">{error}</div>}
      </GlassPanel>

      {weather && (
        <>
          {/* Flight conditions + key atmosphere metrics — single card */}
          <GlassPanel padding="p-3">
            <div className="flex items-center justify-between mb-3">
              <div className="flex-1 min-w-0">
                <h3 className={chartStyles.title}>Conditions</h3>
                <div className="text-white/50 text-[10px] mt-0.5 truncate">{weather.conditions_summary}</div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0 ml-3">
                <div className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: FLIGHT_CAT_COLORS[weather.flight_category] || '#fff' }} />
                <span className="text-lg font-bold font-mono"
                  style={{ color: FLIGHT_CAT_COLORS[weather.flight_category] }}>
                  {weather.flight_category}
                </span>
              </div>
            </div>

            {/* Primary metrics row */}
            <div className="grid grid-cols-3 gap-x-4 gap-y-2">
              <Stat label="Temp" value={weather.temperature_c.toFixed(1)} unit="°C" highlight />
              <Stat label="Pressure" value={weather.pressure_hpa.toFixed(0)} unit="hPa" highlight />
              <Stat label="Density Alt" value={weather.density_altitude_ft.toFixed(0)} unit="ft" highlight />
              <Stat label="Air ρ" value={weather.air_density_kgm3.toFixed(4)} unit="kg/m³" />
              <Stat label="Humidity" value={weather.humidity_pct.toFixed(0)} unit="%" />
              <Stat label="Visibility" value={(weather.visibility_m / 1000).toFixed(1)} unit="km" />
            </div>
          </GlassPanel>

          {/* Wind — compass + altitude profile in one card */}
          <GlassPanel padding="p-3">
            <h3 className={chartStyles.title}>Wind Profile</h3>
            <div className="flex items-start gap-3 mt-2">
              <div className="shrink-0">
                <WindCompass layers={weather.wind_layers} />
              </div>
              <div className="flex-1 min-w-0 pt-1">
                <WindTable layers={weather.wind_layers} />
                <div className="mt-2 flex items-center gap-3 text-[9px] text-white/25">
                  <span>
                    <span className="inline-block w-4 h-1.5 rounded-full bg-white/30 align-middle mr-1" />
                    sustained
                  </span>
                  <span>
                    <span className="inline-block w-4 h-1.5 rounded-full bg-white/[0.08] align-middle mr-1" />
                    gusts
                  </span>
                </div>
              </div>
            </div>
          </GlassPanel>
        </>
      )}

      {solar && (
        <GlassPanel padding="p-3">
          <h3 className={chartStyles.title}>Solar</h3>
          <div className="flex items-center justify-center mt-1">
            <SolarArc data={solar} />
          </div>
          <div className="grid grid-cols-3 gap-x-4 gap-y-2 mt-2">
            <Stat label="Elevation" value={solar.elevation_deg.toFixed(1)} unit="°"
              highlight={solar.is_daytime} />
            <Stat label="Azimuth" value={solar.azimuth_deg.toFixed(0)} unit="°" />
            <Stat label="Day" value={solar.day_length_hr.toFixed(1)} unit="hr" />
            <Stat label="GHI" value={solar.ghi_w_m2.toFixed(0)} unit="W/m²" />
            <Stat label="DNI" value={solar.dni_w_m2.toFixed(0)} unit="W/m²" />
            <Stat
              label="Lux"
              value={solar.illuminance_lux >= 1000
                ? `${(solar.illuminance_lux / 1000).toFixed(1)}k`
                : solar.illuminance_lux.toFixed(0)}
              highlight={solar.is_daytime}
            />
          </div>
        </GlassPanel>
      )}
    </div>
  );
}
