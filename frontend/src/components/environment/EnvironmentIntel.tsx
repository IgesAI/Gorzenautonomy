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
}

const FLIGHT_CAT_COLORS: Record<string, string> = {
  VFR: colors.status.success,
  MVFR: colors.status.info,
  IFR: colors.status.warning,
  LIFR: colors.status.danger,
};

function WindRose({ layer }: { layer: WindLayer }) {
  const r = 32;
  const cx = 40;
  const cy = 40;
  const angle = ((layer.direction_deg - 90) * Math.PI) / 180;
  const len = Math.min(r, (layer.speed_ms / 20) * r);
  const ex = cx + Math.cos(angle) * len;
  const ey = cy + Math.sin(angle) * len;
  const ah = 6;
  const a1x = ex - Math.cos(angle - 0.4) * ah;
  const a1y = ey - Math.sin(angle - 0.4) * ah;
  const a2x = ex - Math.cos(angle + 0.4) * ah;
  const a2y = ey - Math.sin(angle + 0.4) * ah;

  return (
    <div className="flex items-center gap-3">
      <svg width={80} height={80} viewBox="0 0 80 80">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={1} />
        <circle cx={cx} cy={cy} r={r * 0.5} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth={0.5} />
        {['N', 'E', 'S', 'W'].map((d, i) => {
          const a = ((i * 90 - 90) * Math.PI) / 180;
          return (
            <text
              key={d} x={cx + Math.cos(a) * (r + 7)} y={cy + Math.sin(a) * (r + 7)}
              textAnchor="middle" dominantBaseline="central"
              className="fill-white/25 text-[7px] font-mono"
            >{d}</text>
          );
        })}
        <line x1={cx} y1={cy} x2={ex} y2={ey} stroke={colors.accent.primary} strokeWidth={2} strokeLinecap="round" />
        <polygon points={`${ex},${ey} ${a1x},${a1y} ${a2x},${a2y}`} fill={colors.accent.primary} />
      </svg>
      <div>
        <div className="text-white/90 text-sm font-mono font-bold">{layer.speed_ms.toFixed(1)} m/s</div>
        <div className="text-white/40 text-[10px]">{layer.height_m}m AGL</div>
        <div className="text-white/30 text-[10px]">{layer.direction_deg.toFixed(0)}° gusts {layer.gusts_ms.toFixed(1)}</div>
      </div>
    </div>
  );
}

function SolarArc({ data }: { data: SolarData }) {
  const w = 220;
  const h = 80;
  const pad = 20;
  const arcW = w - pad * 2;
  const arcH = h - 20;

  const now = new Date();
  const hourFrac = now.getUTCHours() + now.getUTCMinutes() / 60;
  const dayFrac = Math.max(0, Math.min(1, (hourFrac - data.sunrise_hour) / (data.sunset_hour - data.sunrise_hour + 0.01)));
  const sunAngle = dayFrac * Math.PI;
  const sunX = pad + (1 - Math.cos(sunAngle)) * arcW / 2;
  const sunY = h - 10 - Math.sin(sunAngle) * arcH;

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <line x1={pad} y1={h - 10} x2={w - pad} y2={h - 10} stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
      <path
        d={`M ${pad} ${h - 10} Q ${w / 2} ${10 - arcH * 0.2} ${w - pad} ${h - 10}`}
        fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={1} strokeDasharray="3,3"
      />
      {data.is_daytime && (
        <>
          <circle cx={sunX} cy={sunY} r={10} fill="rgba(251, 191, 36, 0.15)" />
          <circle cx={sunX} cy={sunY} r={5} fill="#fbbf24" />
        </>
      )}
      <text x={pad} y={h - 2} className="fill-white/30 text-[8px] font-mono">
        {data.sunrise_hour.toFixed(1)}h
      </text>
      <text x={w - pad} y={h - 2} textAnchor="end" className="fill-white/30 text-[8px] font-mono">
        {data.sunset_hour.toFixed(1)}h
      </text>
      <text x={w / 2} y={h - 2} textAnchor="middle" className="fill-white/25 text-[8px] font-mono">
        noon {data.solar_noon_utc}
      </text>
    </svg>
  );
}

function MetricCard({ label, value, unit, color }: { label: string; value: string | number; unit?: string; color?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className={chartStyles.label}>{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-lg font-bold font-mono tabular-nums" style={{ color: color || 'rgba(255,255,255,0.95)' }}>
          {value}
        </span>
        {unit && <span className="text-[10px] text-white/40">{unit}</span>}
      </div>
    </div>
  );
}

export function EnvironmentIntel({ onEnvironmentData }: EnvironmentIntelProps) {
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [solar, setSolar] = useState<SolarData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lat, setLat] = useState(35.0);
  const [lon, setLon] = useState(-106.6);
  const [geoStatus, setGeoStatus] = useState<'idle' | 'locating' | 'success' | 'denied'>('idle');

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

      // Push environment snapshot to parent for auto-fill
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
    if (!navigator.geolocation) {
      setGeoStatus('denied');
      return;
    }
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
      () => {
        setGeoStatus('denied');
        // Fall back to default location
        fetchData(lat, lon);
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }, [fetchData, lat, lon]);

  // On mount: try geolocation, fall back to defaults
  useEffect(() => {
    requestGeolocation();
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="h-full overflow-y-auto space-y-3 p-3">
      {/* Location & Fetch Controls */}
      <GlassPanel padding="p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className={chartStyles.title}>Environment Intelligence</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={requestGeolocation}
              disabled={geoStatus === 'locating'}
              className="glass-button text-xs py-1.5 px-3 disabled:opacity-50"
              title="Use browser GPS"
            >
              {geoStatus === 'locating' ? 'Locating...' : 'GPS'}
            </button>
            <button
              onClick={() => fetchData(lat, lon)}
              disabled={loading}
              className="glass-button text-xs py-1.5 px-3 disabled:opacity-50"
            >
              {loading ? 'Fetching...' : 'Refresh'}
            </button>
          </div>
        </div>
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="text-[10px] text-white/40 block mb-1">Latitude</label>
            <input type="number" value={lat} onChange={e => setLat(+e.target.value)} step={0.1}
              className="glass-input text-xs" />
          </div>
          <div className="flex-1">
            <label className="text-[10px] text-white/40 block mb-1">Longitude</label>
            <input type="number" value={lon} onChange={e => setLon(+e.target.value)} step={0.1}
              className="glass-input text-xs" />
          </div>
        </div>
        {geoStatus === 'success' && (
          <div className="mt-2 text-[10px] text-gorzen-400 flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-gorzen-400 animate-pulse" />
            Live GPS position
          </div>
        )}
        {geoStatus === 'denied' && (
          <div className="mt-2 text-[10px] text-white/35">
            GPS unavailable — using manual coordinates
          </div>
        )}
        {error && <div className="mt-2 text-xs text-red-400">{error}</div>}
      </GlassPanel>

      {weather && (
        <>
          {/* Flight Category Banner */}
          <GlassPanel padding="p-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className={chartStyles.title}>Flight Conditions</h3>
                <div className="mt-1 text-white/60 text-xs">{weather.conditions_summary}</div>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: FLIGHT_CAT_COLORS[weather.flight_category] || '#fff' }}
                />
                <span className="text-xl font-bold font-mono" style={{ color: FLIGHT_CAT_COLORS[weather.flight_category] }}>
                  {weather.flight_category}
                </span>
              </div>
            </div>
          </GlassPanel>

          {/* Atmosphere Metrics */}
          <GlassPanel padding="p-4">
            <h3 className={chartStyles.title}>Atmosphere</h3>
            <div className="grid grid-cols-3 gap-4 mt-3">
              <MetricCard label="Temperature" value={weather.temperature_c} unit="°C" />
              <MetricCard label="Pressure" value={weather.pressure_hpa} unit="hPa" />
              <MetricCard label="Humidity" value={weather.humidity_pct} unit="%" />
              <MetricCard label="Air Density" value={weather.air_density_kgm3.toFixed(4)} unit="kg/m³" />
              <MetricCard label="Density Alt" value={weather.density_altitude_ft.toFixed(0)} unit="ft" />
              <MetricCard label="Visibility" value={(weather.visibility_m / 1000).toFixed(1)} unit="km" />
            </div>
          </GlassPanel>

          {/* Wind Profile */}
          <GlassPanel padding="p-4">
            <h3 className={chartStyles.title}>Wind Profile (Multi-Altitude)</h3>
            <div className="grid grid-cols-2 gap-3 mt-3">
              {weather.wind_layers.map(layer => (
                <WindRose key={layer.height_m} layer={layer} />
              ))}
            </div>
            <div className="mt-4 space-y-1.5">
              {weather.wind_layers.map(layer => {
                const pct = Math.min(100, (layer.speed_ms / 25) * 100);
                const gustPct = Math.min(100, (layer.gusts_ms / 25) * 100);
                return (
                  <div key={layer.height_m} className="flex items-center gap-2">
                    <span className="text-[10px] text-white/40 font-mono w-10 text-right">{layer.height_m}m</span>
                    <div className="flex-1 h-3 rounded-full bg-white/[0.04] relative overflow-hidden">
                      <div className="absolute inset-y-0 left-0 rounded-full opacity-30"
                        style={{ width: `${gustPct}%`, backgroundColor: colors.accent.primary }} />
                      <div className="absolute inset-y-0 left-0 rounded-full"
                        style={{ width: `${pct}%`, backgroundColor: colors.accent.primary }} />
                    </div>
                    <span className="text-[10px] text-white/60 font-mono w-12">{layer.speed_ms.toFixed(1)} m/s</span>
                  </div>
                );
              })}
            </div>
          </GlassPanel>
        </>
      )}

      {solar && (
        <GlassPanel padding="p-4">
          <h3 className={chartStyles.title}>Solar Position</h3>
          <div className="flex items-center justify-center mt-2">
            <SolarArc data={solar} />
          </div>
          <div className="grid grid-cols-3 gap-4 mt-3">
            <MetricCard label="Elevation" value={solar.elevation_deg.toFixed(1)} unit="°" />
            <MetricCard label="Azimuth" value={solar.azimuth_deg.toFixed(1)} unit="°" />
            <MetricCard label="Day Length" value={solar.day_length_hr.toFixed(1)} unit="hr" />
            <MetricCard label="GHI" value={solar.ghi_w_m2.toFixed(0)} unit="W/m²" />
            <MetricCard label="DNI" value={solar.dni_w_m2.toFixed(0)} unit="W/m²" />
            <MetricCard
              label="Illuminance"
              value={solar.illuminance_lux >= 1000 ? (solar.illuminance_lux / 1000).toFixed(1) + 'k' : solar.illuminance_lux.toFixed(0)}
              unit="lux"
              color={solar.is_daytime ? '#fbbf24' : '#64748b'}
            />
          </div>
        </GlassPanel>
      )}
    </div>
  );
}
