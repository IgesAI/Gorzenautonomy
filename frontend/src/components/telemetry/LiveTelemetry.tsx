import React, { useState, useEffect, useRef, useCallback } from 'react';
import { GlassPanel } from '../layout/GlassPanel';
import { chartStyles } from '../../theme/chartStyles';
import { colors, getConfidenceColor } from '../../theme/tokens';
import { api } from '../../api/client';

interface TelemetrySnapshot {
  timestamp: number;
  position: { latitude_deg: number; longitude_deg: number; absolute_altitude_m: number; relative_altitude_m: number };
  attitude: { roll_deg: number; pitch_deg: number; yaw_deg: number };
  velocity: { groundspeed_ms: number; airspeed_ms: number; climb_rate_ms: number };
  battery: { voltage_v: number; current_a: number; remaining_pct: number; temperature_c: number | null };
  gps: { fix_type: string; num_satellites: number; hdop: number };
  wind: { speed_ms: number; direction_deg: number };
  status: { flight_mode: string; armed: boolean; in_air: boolean; health_ok: boolean };
  connection: { connected: boolean; address: string; uptime_s: number; messages_received: number };
}

interface ParamMapping {
  twin_subsystem: string;
  twin_param: string;
  px4_param: string;
  px4_description: string;
  px4_group: string;
  px4_unit: string;
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-2 h-2 rounded-full ${ok ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'}`} />
      <span className="text-[10px] text-white/60">{label}</span>
    </div>
  );
}

function TelemetryGauge({ label, value, unit, color, min, max }: {
  label: string; value: number; unit: string; color?: string; min?: number; max?: number;
}) {
  const pct = min !== undefined && max !== undefined
    ? Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100))
    : 0;

  return (
    <div className="flex flex-col gap-1">
      <div className={chartStyles.label}>{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-lg font-bold font-mono tabular-nums" style={{ color: color || 'rgba(255,255,255,0.95)' }}>
          {typeof value === 'number' ? value.toFixed(1) : value}
        </span>
        <span className="text-[10px] text-white/40">{unit}</span>
      </div>
      {min !== undefined && max !== undefined && (
        <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
          <div className="h-full rounded-full transition-all duration-300" style={{ width: `${pct}%`, backgroundColor: color || colors.accent.primary }} />
        </div>
      )}
    </div>
  );
}

function AttitudeIndicator({ roll, pitch }: { roll: number; pitch: number }) {
  const cx = 50, cy = 50, r = 40;
  const pitchOffset = Math.max(-r, Math.min(r, pitch * 0.8));

  return (
    <svg width={100} height={100} viewBox="0 0 100 100">
      <defs>
        <clipPath id="atti-clip"><circle cx={cx} cy={cy} r={r} /></clipPath>
      </defs>
      <circle cx={cx} cy={cy} r={r} fill="rgba(255,255,255,0.04)" stroke="rgba(255,255,255,0.12)" strokeWidth={1} />
      <g clipPath="url(#atti-clip)" transform={`rotate(${-roll}, ${cx}, ${cy})`}>
        <rect x={0} y={cy + pitchOffset} width={100} height={50} fill="rgba(139,92,46,0.3)" />
        <rect x={0} y={0} width={100} height={cy + pitchOffset} fill="rgba(59,130,246,0.2)" />
        <line x1={10} y1={cy + pitchOffset} x2={90} y2={cy + pitchOffset} stroke="rgba(255,255,255,0.5)" strokeWidth={1} />
      </g>
      {/* Aircraft symbol */}
      <line x1={cx - 20} y1={cy} x2={cx - 6} y2={cy} stroke="#fbbf24" strokeWidth={2} />
      <line x1={cx + 6} y1={cy} x2={cx + 20} y2={cy} stroke="#fbbf24" strokeWidth={2} />
      <circle cx={cx} cy={cy} r={3} fill="none" stroke="#fbbf24" strokeWidth={1.5} />
    </svg>
  );
}

export function LiveTelemetry() {
  const [snapshot, setSnapshot] = useState<TelemetrySnapshot | null>(null);
  const [connectionAddr, setConnectionAddr] = useState('udp://:14540');
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState(false);
  const [paramMap, setParamMap] = useState<ParamMapping[]>([]);
  const [showParams, setShowParams] = useState(false);
  const pollRef = useRef<number | null>(null);

  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    const poll = async () => {
      try {
        const data = await api.telemetry.snapshot();
        setSnapshot(data);
        setConnected(data.connection?.connected ?? false);
      } catch { /* ignore */ }
    };
    poll();
    pollRef.current = window.setInterval(poll, 500);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const handleConnect = async () => {
    setConnecting(true);
    try {
      const res = await api.telemetry.connect(connectionAddr);
      setConnected(res.connected);
      if (res.connected) startPolling();
    } catch { /* ignore */ }
    setConnecting(false);
  };

  const handleDisconnect = async () => {
    stopPolling();
    await api.telemetry.disconnect();
    setConnected(false);
    setSnapshot(null);
  };

  useEffect(() => {
    // Check if already connected
    api.telemetry.status().then(s => {
      if (s.connected) { setConnected(true); startPolling(); }
    }).catch(() => {});
    // Load param map
    api.telemetry.paramMap().then(d => setParamMap(d.mappings || [])).catch(() => {});
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  const s = snapshot;
  const battColor = s ? (s.battery.remaining_pct > 50 ? colors.status.success : s.battery.remaining_pct > 20 ? colors.status.warning : colors.status.danger) : '#fff';

  return (
    <div className="h-full overflow-y-auto space-y-3 p-3">
      {/* Connection */}
      <GlassPanel padding="p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className={chartStyles.title}>MAVLink Telemetry</h2>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400 animate-pulse' : 'bg-white/20'}`} />
            <span className="text-[10px] text-white/50">{connected ? 'CONNECTED' : 'OFFLINE'}</span>
          </div>
        </div>
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <label className="text-[10px] text-white/40 block mb-1">Connection Address</label>
            <input
              type="text" value={connectionAddr} onChange={e => setConnectionAddr(e.target.value)}
              placeholder="udp://:14540" className="glass-input text-xs" disabled={connected}
            />
          </div>
          {!connected ? (
            <button onClick={handleConnect} disabled={connecting} className="glass-button text-xs py-2 px-4 disabled:opacity-50">
              {connecting ? 'Connecting...' : 'Connect'}
            </button>
          ) : (
            <button onClick={handleDisconnect} className="glass-button text-xs py-2 px-4 border-red-500/30 text-red-400">
              Disconnect
            </button>
          )}
        </div>
        <div className="mt-2 flex gap-3 text-[10px] text-white/35">
          <span>SITL: udp://:14540</span>
          <span>Radio: serial:///dev/ttyUSB0:57600</span>
          <span>WiFi: udp://192.168.x.x:14550</span>
        </div>
      </GlassPanel>

      {s && (
        <>
          {/* Flight Status Bar */}
          <GlassPanel padding="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <StatusBadge ok={s.status.armed} label={s.status.armed ? 'ARMED' : 'DISARMED'} />
                <StatusBadge ok={s.status.in_air} label={s.status.in_air ? 'IN AIR' : 'ON GROUND'} />
                <StatusBadge ok={s.status.health_ok} label={s.status.health_ok ? 'HEALTHY' : 'FAULT'} />
              </div>
              <div className="text-sm font-bold font-mono text-gorzen-400">
                {s.status.flight_mode}
              </div>
            </div>
          </GlassPanel>

          {/* Attitude + Position */}
          <GlassPanel padding="p-4">
            <h3 className={chartStyles.title}>Attitude & Position</h3>
            <div className="flex items-center gap-4 mt-3">
              <AttitudeIndicator roll={s.attitude.roll_deg} pitch={s.attitude.pitch_deg} />
              <div className="flex-1 grid grid-cols-3 gap-3">
                <TelemetryGauge label="Roll" value={s.attitude.roll_deg} unit="deg" />
                <TelemetryGauge label="Pitch" value={s.attitude.pitch_deg} unit="deg" />
                <TelemetryGauge label="Yaw" value={s.attitude.yaw_deg} unit="deg" />
                <TelemetryGauge label="Lat" value={s.position.latitude_deg} unit="deg" />
                <TelemetryGauge label="Lon" value={s.position.longitude_deg} unit="deg" />
                <TelemetryGauge label="Alt AGL" value={s.position.relative_altitude_m} unit="m" />
              </div>
            </div>
          </GlassPanel>

          {/* Velocity */}
          <GlassPanel padding="p-4">
            <h3 className={chartStyles.title}>Velocity</h3>
            <div className="grid grid-cols-3 gap-4 mt-3">
              <TelemetryGauge label="Groundspeed" value={s.velocity.groundspeed_ms} unit="m/s" color={colors.accent.primary} min={0} max={35} />
              <TelemetryGauge label="Airspeed" value={s.velocity.airspeed_ms} unit="m/s" color="#06b6d4" min={0} max={35} />
              <TelemetryGauge label="Climb Rate" value={s.velocity.climb_rate_ms} unit="m/s" />
            </div>
          </GlassPanel>

          {/* Battery */}
          <GlassPanel padding="p-4">
            <h3 className={chartStyles.title}>Battery</h3>
            <div className="grid grid-cols-3 gap-4 mt-3">
              <TelemetryGauge label="Voltage" value={s.battery.voltage_v} unit="V" color={battColor} min={36} max={50} />
              <TelemetryGauge label="Current" value={s.battery.current_a} unit="A" min={0} max={50} />
              <TelemetryGauge label="Remaining" value={s.battery.remaining_pct} unit="%" color={battColor} min={0} max={100} />
            </div>
          </GlassPanel>

          {/* GPS + Wind */}
          <GlassPanel padding="p-4">
            <h3 className={chartStyles.title}>GPS & Wind</h3>
            <div className="grid grid-cols-4 gap-4 mt-3">
              <TelemetryGauge label="Fix" value={s.gps.fix_type as any} unit="" />
              <TelemetryGauge label="Satellites" value={s.gps.num_satellites} unit="" color={s.gps.num_satellites >= 10 ? colors.status.success : colors.status.warning} />
              <TelemetryGauge label="Wind" value={s.wind.speed_ms} unit="m/s" />
              <TelemetryGauge label="Wind Dir" value={s.wind.direction_deg} unit="deg" />
            </div>
          </GlassPanel>
        </>
      )}

      {/* PX4 Parameter Map */}
      <GlassPanel padding="p-4">
        <div className="flex items-center justify-between">
          <h3 className={chartStyles.title}>PX4 Parameter Map</h3>
          <button onClick={() => setShowParams(!showParams)} className="glass-button text-[10px] py-1 px-2">
            {showParams ? 'Hide' : `Show (${paramMap.length})`}
          </button>
        </div>
        {showParams && (
          <div className="mt-3 space-y-1 max-h-60 overflow-y-auto">
            {paramMap.map((m, i) => (
              <div key={i} className="flex items-center justify-between py-1 border-b border-white/[0.04]">
                <div className="flex-1 min-w-0">
                  <span className="text-[10px] font-mono text-gorzen-400">{m.px4_param}</span>
                  <span className="text-[10px] text-white/30 ml-2">{m.px4_description}</span>
                </div>
                <span className="text-[10px] font-mono text-white/50 flex-shrink-0 ml-2">
                  {m.twin_subsystem}.{m.twin_param}
                </span>
              </div>
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  );
}
