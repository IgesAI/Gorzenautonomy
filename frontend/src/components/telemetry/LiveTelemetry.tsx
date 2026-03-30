import { useState, useEffect, useRef, useCallback, useId, useMemo } from 'react';
import { GlassPanel } from '../layout/GlassPanel';
import { chartStyles } from '../../theme/chartStyles';
import { colors } from '../../theme/tokens';
import { api } from '../../api/client';
import type { TelemetrySnapshot, ParamMapping } from '../../types/api';

const GPS_FIX_LABELS: Record<string, string> = {
  '0': 'No GPS', '1': 'No Fix', '2': '2D Fix', '3': '3D Fix',
  '4': 'DGPS', '5': 'RTK Float', '6': 'RTK Fixed',
  'NO_FIX': 'No Fix', 'FIX_2D': '2D Fix', 'FIX_3D': '3D Fix',
  'FIX_DGPS': 'DGPS', 'RTK_FLOAT': 'RTK Float', 'RTK_FIXED': 'RTK Fixed',
};

const ARDUPILOT_MODES: Record<string, string> = {
  '0': 'STABILIZE', '1': 'ACRO', '2': 'ALT HOLD', '3': 'AUTO',
  '4': 'GUIDED', '5': 'LOITER', '6': 'RTL', '7': 'CIRCLE',
  '9': 'LAND', '11': 'DRIFT', '13': 'SPORT', '14': 'FLIP',
  '15': 'AUTOTUNE', '16': 'POSHOLD', '17': 'BRAKE', '18': 'THROW',
  '19': 'AVOID_ADSB', '20': 'GUIDED_NOGPS', '21': 'SMART_RTL',
};

function formatCoord(deg: number, isLat: boolean): string {
  const dir = isLat ? (deg >= 0 ? 'N' : 'S') : (deg >= 0 ? 'E' : 'W');
  const abs = Math.abs(deg);
  const d = Math.floor(abs);
  const m = ((abs - d) * 60).toFixed(4);
  return `${d}\u00B0${m}'${dir}`;
}

function ArcGauge({ value, min, max, label, unit, color, size = 80, thresholds }: {
  value: number; min: number; max: number; label: string; unit: string;
  color: string; size?: number; thresholds?: { warn: number; danger: number; invert?: boolean };
}) {
  const pct = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const startAngle = -225;
  const sweep = 270;
  const angle = startAngle + pct * sweep;
  const r = size * 0.38;
  const cx = size / 2, cy = size / 2;
  const trackWidth = size * 0.06;

  let gaugeColor = color;
  if (thresholds) {
    const { warn, danger, invert } = thresholds;
    if (invert) {
      if (value <= danger) gaugeColor = colors.status.danger;
      else if (value <= warn) gaugeColor = colors.status.warning;
    } else {
      if (value >= danger) gaugeColor = colors.status.danger;
      else if (value >= warn) gaugeColor = colors.status.warning;
    }
  }

  const arcPath = (startDeg: number, endDeg: number) => {
    const s = (startDeg * Math.PI) / 180;
    const e = (endDeg * Math.PI) / 180;
    const x1 = cx + r * Math.cos(s), y1 = cy + r * Math.sin(s);
    const x2 = cx + r * Math.cos(e), y2 = cy + r * Math.sin(e);
    const large = Math.abs(endDeg - startDeg) > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
  };

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size * 0.78} viewBox={`0 0 ${size} ${size * 0.78}`}>
        <path d={arcPath(startAngle, startAngle + sweep)} fill="none"
          stroke="rgba(255,255,255,0.06)" strokeWidth={trackWidth} strokeLinecap="round" />
        {pct > 0.005 && (
          <path d={arcPath(startAngle, angle)} fill="none"
            stroke={gaugeColor} strokeWidth={trackWidth} strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 4px ${gaugeColor}60)`, transition: 'all 0.3s ease' }} />
        )}
        <text x={cx} y={cy - 2} textAnchor="middle" dominantBaseline="central"
          fill="rgba(255,255,255,0.95)" fontSize={size * 0.2} fontFamily="monospace" fontWeight="bold">
          {value.toFixed(1)}
        </text>
        <text x={cx} y={cy + size * 0.14} textAnchor="middle"
          fill="rgba(255,255,255,0.35)" fontSize={size * 0.1} fontFamily="monospace">
          {unit}
        </text>
      </svg>
      <span className="text-[9px] uppercase tracking-wider text-white/40 -mt-1">{label}</span>
    </div>
  );
}

function AttitudeIndicator({ roll, pitch }: { roll: number; pitch: number }) {
  const clipId = useId();
  const size = 140;
  const cx = size / 2, cy = size / 2, r = 58;
  const pitchOffset = Math.max(-r, Math.min(r, pitch * 0.8));
  const tickR = r + 6;

  return (
    <div className="relative">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <defs>
          <clipPath id={clipId}><circle cx={cx} cy={cy} r={r} /></clipPath>
          <radialGradient id={`${clipId}-sky`} cx="50%" cy="100%">
            <stop offset="0%" stopColor="rgba(59,130,246,0.25)" />
            <stop offset="100%" stopColor="rgba(30,64,175,0.15)" />
          </radialGradient>
          <radialGradient id={`${clipId}-gnd`} cx="50%" cy="0%">
            <stop offset="0%" stopColor="rgba(139,92,46,0.35)" />
            <stop offset="100%" stopColor="rgba(92,55,20,0.2)" />
          </radialGradient>
        </defs>
        <circle cx={cx} cy={cy} r={r + 2} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
        <circle cx={cx} cy={cy} r={r} fill="rgba(0,0,0,0.4)" />
        <g clipPath={`url(#${clipId})`} transform={`rotate(${-roll}, ${cx}, ${cy})`}>
          <rect x={0} y={0} width={size} height={cy + pitchOffset} fill={`url(#${clipId}-sky)`} />
          <rect x={0} y={cy + pitchOffset} width={size} height={size} fill={`url(#${clipId}-gnd)`} />
          <line x1={10} y1={cy + pitchOffset} x2={size - 10} y2={cy + pitchOffset}
            stroke="rgba(255,255,255,0.6)" strokeWidth={1.5} />
          {[-20, -10, 10, 20].map(deg => {
            const y = cy + pitchOffset - deg * 0.8;
            const w = Math.abs(deg) === 20 ? 16 : 22;
            return (
              <g key={deg}>
                <line x1={cx - w} y1={y} x2={cx + w} y2={y}
                  stroke="rgba(255,255,255,0.25)" strokeWidth={1} />
                <text x={cx + w + 4} y={y + 3} fill="rgba(255,255,255,0.25)"
                  fontSize={7} fontFamily="monospace">{Math.abs(deg)}</text>
              </g>
            );
          })}
        </g>
        {[0, 30, 60, 90, -30, -60, -90].map(deg => {
          const a = ((deg - 90) * Math.PI) / 180;
          const len = deg % 30 === 0 && deg !== 0 ? 4 : 6;
          return (
            <line key={deg}
              x1={cx + (tickR - len) * Math.cos(a)} y1={cy + (tickR - len) * Math.sin(a)}
              x2={cx + tickR * Math.cos(a)} y2={cy + tickR * Math.sin(a)}
              stroke="rgba(255,255,255,0.2)" strokeWidth={1} />
          );
        })}
        <polygon points={`${cx},${cy - r - 8} ${cx - 4},${cy - r - 2} ${cx + 4},${cy - r - 2}`}
          fill="#fbbf24" />
        <line x1={cx - 28} y1={cy} x2={cx - 8} y2={cy} stroke="#fbbf24" strokeWidth={2.5} strokeLinecap="round" />
        <line x1={cx + 8} y1={cy} x2={cx + 28} y2={cy} stroke="#fbbf24" strokeWidth={2.5} strokeLinecap="round" />
        <line x1={cx - 8} y1={cy} x2={cx - 4} y2={cy + 5} stroke="#fbbf24" strokeWidth={2} strokeLinecap="round" />
        <line x1={cx + 8} y1={cy} x2={cx + 4} y2={cy + 5} stroke="#fbbf24" strokeWidth={2} strokeLinecap="round" />
        <circle cx={cx} cy={cy} r={2.5} fill="#fbbf24" />
      </svg>
      <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 flex gap-3">
        <span className="text-[9px] font-mono text-white/40">R {roll.toFixed(1)}&deg;</span>
        <span className="text-[9px] font-mono text-white/40">P {pitch.toFixed(1)}&deg;</span>
      </div>
    </div>
  );
}

function HeadingCompass({ heading }: { heading: number }) {
  const size = 140;
  const cx = size / 2, cy = size / 2, r = 56;
  const clipId = useId();
  const cardinals = [
    { deg: 0, label: 'N', color: '#ef4444' },
    { deg: 90, label: 'E', color: 'rgba(255,255,255,0.5)' },
    { deg: 180, label: 'S', color: 'rgba(255,255,255,0.5)' },
    { deg: 270, label: 'W', color: 'rgba(255,255,255,0.5)' },
  ];

  return (
    <div className="relative">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={cx} cy={cy} r={r + 2} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
        <circle cx={cx} cy={cy} r={r} fill="rgba(0,0,0,0.3)" />
        <g transform={`rotate(${-heading}, ${cx}, ${cy})`}>
          {Array.from({ length: 36 }, (_, i) => {
            const deg = i * 10;
            const a = ((deg - 90) * Math.PI) / 180;
            const isMajor = deg % 30 === 0;
            const len = isMajor ? 8 : 4;
            return (
              <line key={deg}
                x1={cx + (r - len) * Math.cos(a)} y1={cy + (r - len) * Math.sin(a)}
                x2={cx + r * Math.cos(a)} y2={cy + r * Math.sin(a)}
                stroke={isMajor ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.12)'}
                strokeWidth={isMajor ? 1.5 : 0.8} />
            );
          })}
          {cardinals.map(({ deg, label, color }) => {
            const a = ((deg - 90) * Math.PI) / 180;
            const labelR = r - 16;
            return (
              <text key={deg}
                x={cx + labelR * Math.cos(a)} y={cy + labelR * Math.sin(a) + 3}
                textAnchor="middle" fill={color} fontSize={11} fontWeight="bold" fontFamily="monospace">
                {label}
              </text>
            );
          })}
        </g>
        <polygon points={`${cx},${cy - 20} ${cx - 5},${cy - 6} ${cx + 5},${cy - 6}`}
          fill="#ef4444" style={{ filter: 'drop-shadow(0 0 3px rgba(239,68,68,0.5))' }} />
        <polygon points={`${cx},${cy + 20} ${cx - 5},${cy + 6} ${cx + 5},${cy + 6}`}
          fill="rgba(255,255,255,0.2)" />
        <circle cx={cx} cy={cy} r={3} fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.2)" strokeWidth={1} />
      </svg>
      <div className="absolute -bottom-1 left-1/2 -translate-x-1/2">
        <span className="text-[10px] font-mono font-bold text-white/70">{heading.toFixed(0)}&deg;</span>
      </div>
    </div>
  );
}

function StatCell({ label, value, unit, color, glow }: {
  label: string; value: string; unit?: string; color?: string; glow?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5 px-2 py-1.5 rounded-lg bg-white/[0.02] border border-white/[0.04]">
      <span className="text-[8px] uppercase tracking-widest text-white/35">{label}</span>
      <div className="flex items-baseline gap-1">
        <span className="text-sm font-bold font-mono tabular-nums transition-all duration-300"
          style={{
            color: color || 'rgba(255,255,255,0.9)',
            textShadow: glow ? `0 0 8px ${color}60` : undefined,
          }}>
          {value}
        </span>
        {unit && <span className="text-[8px] text-white/30 font-mono">{unit}</span>}
      </div>
    </div>
  );
}

function SignalBars({ strength, label }: { strength: number; label: string }) {
  const bars = 5;
  const filledBars = Math.round((strength / 100) * bars);
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="flex items-end gap-[2px] h-4">
        {Array.from({ length: bars }, (_, i) => (
          <div key={i}
            className="w-[3px] rounded-sm transition-all duration-300"
            style={{
              height: `${40 + i * 15}%`,
              backgroundColor: i < filledBars
                ? (filledBars <= 2 ? colors.status.danger : filledBars <= 3 ? colors.status.warning : colors.status.success)
                : 'rgba(255,255,255,0.08)',
            }} />
        ))}
      </div>
      <span className="text-[8px] text-white/35 uppercase tracking-wider">{label}</span>
    </div>
  );
}

interface LiveTelemetryProps {
  onTelemetryUpdate?: (data: { wind_speed_ms: number; temperature_c: number }) => void;
}

export function LiveTelemetry({ onTelemetryUpdate }: LiveTelemetryProps) {
  const [snapshot, setSnapshot] = useState<TelemetrySnapshot | null>(null);
  const [connectionAddr, setConnectionAddr] = useState('serial://COM6:57600');
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [paramMap, setParamMap] = useState<ParamMapping[]>([]);
  const [showParams, setShowParams] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msgRate, setMsgRate] = useState(0);
  const prevMsgCount = useRef(0);
  const prevMsgTime = useRef(Date.now());
  const pollRef = useRef<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const processSnapshot = useCallback((data: TelemetrySnapshot) => {
    setSnapshot(data);
    setConnected(data.connection?.connected ?? false);
    const now = Date.now();
    const dt = (now - prevMsgTime.current) / 1000;
    if (dt > 0.5) {
      const count = data.connection?.messages_received ?? 0;
      setMsgRate(Math.round((count - prevMsgCount.current) / dt));
      prevMsgCount.current = count;
      prevMsgTime.current = now;
    }
    if (onTelemetryUpdate && data.connection?.connected) {
      onTelemetryUpdate({ wind_speed_ms: data.wind?.speed_ms ?? 0, temperature_c: 15 });
    }
  }, [onTelemetryUpdate]);

  const startWebSocket = useCallback(() => {
    if (wsRef.current) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/telemetry/ws`;
    try {
      const ws = new WebSocket(wsUrl);
      ws.onmessage = (event) => {
        try { processSnapshot(JSON.parse(event.data) as TelemetrySnapshot); } catch {}
      };
      ws.onerror = () => { ws.close(); wsRef.current = null; if (connected) startPolling(); };
      ws.onclose = () => { wsRef.current = null; };
      wsRef.current = ws;
    } catch { startPolling(); }
  }, [processSnapshot]);

  const startPolling = useCallback(() => {
    if (pollRef.current || wsRef.current) return;
    const poll = async () => {
      try { const data = await api.telemetry.snapshot(); processSnapshot(data); setError(null); }
      catch (e) { setError(e instanceof Error ? e.message : 'Telemetry fetch failed'); }
    };
    poll();
    pollRef.current = window.setInterval(poll, 500);
  }, [processSnapshot]);

  const stopAll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
  }, []);

  const handleConnect = async () => {
    if (abortRef.current) abortRef.current.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setConnecting(true); setError(null);
    try {
      const res = await api.telemetry.connect(connectionAddr);
      if (ac.signal.aborted) return;
      setConnected(res.connected);
      if (res.connected) startWebSocket();
    } catch (e) {
      if (ac.signal.aborted) return;
      setError(e instanceof Error ? e.message : 'Connection failed');
    } finally {
      if (!ac.signal.aborted) setConnecting(false);
      abortRef.current = null;
    }
  };

  const handleDisconnect = async () => {
    if (abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
    setDisconnecting(true);
    stopAll();
    try { await api.telemetry.disconnect(); } catch {}
    setConnected(false);
    setConnecting(false);
    setSnapshot(null);
    setMsgRate(0);
    setError(null);
    prevMsgCount.current = 0;
    prevMsgTime.current = Date.now();
    setDisconnecting(false);
  };

  useEffect(() => {
    api.telemetry.status().then(s => {
      if (s.connected) { setConnected(true); startWebSocket(); }
    }).catch(() => {});
    api.telemetry.paramMap().then(d => setParamMap(d.mappings || [])).catch(() => {});
    return () => {
      stopAll();
      api.telemetry.disconnect().catch(() => {});
    };
  }, [startWebSocket, stopAll]);

  const s = snapshot;
  const battPct = s?.battery.remaining_pct ?? 0;
  const battColor = battPct > 50 ? colors.status.success : battPct > 20 ? colors.status.warning : colors.status.danger;
  const gpsColor = (s?.gps.num_satellites ?? 0) >= 10 ? colors.status.success
    : (s?.gps.num_satellites ?? 0) >= 6 ? colors.status.warning : colors.status.danger;
  const flightMode = s ? (ARDUPILOT_MODES[s.status.flight_mode] || s.status.flight_mode) : 'UNKNOWN';
  const uptime = s?.connection?.uptime_s ?? 0;
  const uptimeStr = uptime > 0 ? `${Math.floor(uptime / 60)}:${String(Math.floor(uptime % 60)).padStart(2, '0')}` : '--:--';

  return (
    <div className="h-full overflow-y-auto space-y-2.5 p-3">
      {/* Connection Header */}
      <GlassPanel padding="p-3">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-2.5">
            <div className="relative">
              <div className={`w-2.5 h-2.5 rounded-full ${connected ? 'bg-emerald-400' : 'bg-white/15'}`} />
              {connected && <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping opacity-40" />}
            </div>
            <span className="text-[10px] font-mono font-bold tracking-wider text-white/60">
              {connected ? 'LINK ACTIVE' : 'NO LINK'}
            </span>
          </div>
          {connected && (
            <div className="flex items-center gap-3 text-[9px] font-mono text-white/35">
              <span>{msgRate} msg/s</span>
              <span>{uptimeStr}</span>
              <span>{s?.connection?.messages_received ?? 0} total</span>
            </div>
          )}
        </div>
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <input type="text" value={connectionAddr} onChange={e => setConnectionAddr(e.target.value)}
              placeholder="serial://COM6:57600" className="glass-input text-xs font-mono" disabled={connected} />
          </div>
          {!connected ? (
            <button onClick={handleConnect} disabled={connecting}
              className="glass-button text-xs py-2 px-5 disabled:opacity-50 font-mono tracking-wider">
              {connecting ? 'LINKING...' : 'CONNECT'}
            </button>
          ) : (
            <button onClick={handleDisconnect} disabled={disconnecting}
              className="glass-button text-xs py-2 px-4 border-red-500/20 text-red-400 font-mono tracking-wider disabled:opacity-50">
              {disconnecting ? 'CLOSING...' : 'DISCONNECT'}
            </button>
          )}
        </div>
        {error && (
          <div className="mt-2 p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-[10px] text-red-400 font-mono">{error}</div>
        )}
      </GlassPanel>

      {s && (
        <>
          {/* Flight Mode + Status Strip */}
          <div className="flex gap-2">
            <GlassPanel padding="p-3" className="flex-1">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {[
                    { ok: s.status.armed, on: 'ARMED', off: 'DISARMED', dangerOn: true },
                    { ok: s.status.in_air, on: 'AIRBORNE', off: 'GROUND' },
                    { ok: s.status.health_ok, on: 'SYS OK', off: 'FAULT' },
                  ].map(({ ok, on, off, dangerOn }) => (
                    <div key={on} className="flex items-center gap-1.5">
                      <div className={`w-1.5 h-1.5 rounded-full ${ok ? (dangerOn ? 'bg-red-400' : 'bg-emerald-400') : 'bg-white/15'}`}
                        style={ok ? { boxShadow: `0 0 6px ${dangerOn ? 'rgba(239,68,68,0.5)' : 'rgba(16,185,129,0.5)'}` } : undefined} />
                      <span className={`text-[9px] font-mono tracking-wider ${ok ? 'text-white/70' : 'text-white/30'}`}>
                        {ok ? on : off}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="px-3 py-1 rounded-md bg-white/[0.06] border border-white/[0.08]">
                  <span className="text-xs font-mono font-bold tracking-wider text-white/90"
                    style={{ textShadow: '0 0 10px rgba(255,255,255,0.15)' }}>
                    {flightMode}
                  </span>
                </div>
              </div>
            </GlassPanel>
          </div>

          {/* HUD Row: Attitude + Heading + Key Stats */}
          <div className="flex gap-2.5">
            <GlassPanel padding="p-3" className="flex flex-col items-center justify-center">
              <span className="text-[8px] uppercase tracking-widest text-white/30 mb-1">ATTITUDE</span>
              <AttitudeIndicator roll={s.attitude.roll_deg} pitch={s.attitude.pitch_deg} />
            </GlassPanel>
            <GlassPanel padding="p-3" className="flex flex-col items-center justify-center">
              <span className="text-[8px] uppercase tracking-widest text-white/30 mb-1">HEADING</span>
              <HeadingCompass heading={s.attitude.yaw_deg < 0 ? s.attitude.yaw_deg + 360 : s.attitude.yaw_deg} />
            </GlassPanel>
            <GlassPanel padding="p-3" className="flex-1">
              <span className="text-[8px] uppercase tracking-widest text-white/30">POSITION</span>
              <div className="mt-2 space-y-1.5">
                <StatCell label="LATITUDE" value={formatCoord(s.position.latitude_deg, true)} />
                <StatCell label="LONGITUDE" value={formatCoord(s.position.longitude_deg, false)} />
                <div className="grid grid-cols-2 gap-1.5">
                  <StatCell label="ALT MSL" value={s.position.absolute_altitude_m.toFixed(1)} unit="m" />
                  <StatCell label="ALT AGL" value={s.position.relative_altitude_m.toFixed(1)} unit="m"
                    color={s.position.relative_altitude_m > 0 ? '#60a5fa' : undefined} />
                </div>
              </div>
            </GlassPanel>
          </div>

          {/* Velocity Gauges */}
          <GlassPanel padding="p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[8px] uppercase tracking-widest text-white/30">VELOCITY</span>
              <span className="text-[9px] font-mono text-white/25">
                N:{s.velocity.velocity_north_ms.toFixed(1)} E:{s.velocity.velocity_east_ms.toFixed(1)} D:{s.velocity.velocity_down_ms.toFixed(1)}
              </span>
            </div>
            <div className="flex items-center justify-around">
              <ArcGauge value={s.velocity.groundspeed_ms} min={0} max={40}
                label="GND SPEED" unit="m/s" color="#ffffff" size={100} />
              <ArcGauge value={s.velocity.airspeed_ms} min={0} max={40}
                label="AIR SPEED" unit="m/s" color="#06b6d4" size={100} />
              <ArcGauge value={s.velocity.climb_rate_ms} min={-10} max={10}
                label="V/S" unit="m/s" color="#a78bfa" size={100} />
            </div>
          </GlassPanel>

          {/* Battery */}
          <GlassPanel padding="p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[8px] uppercase tracking-widest text-white/30">POWER</span>
              <div className="flex items-center gap-1.5">
                <div className="w-6 h-2.5 rounded-sm border border-white/15 relative overflow-hidden">
                  <div className="absolute inset-0.5 rounded-[1px] transition-all duration-500"
                    style={{
                      width: `${battPct}%`,
                      backgroundColor: battColor,
                      boxShadow: `0 0 4px ${battColor}50`,
                    }} />
                </div>
                <div className="w-0.5 h-1.5 rounded-r-sm bg-white/15" />
                <span className="text-[10px] font-mono font-bold ml-1" style={{ color: battColor }}>
                  {battPct.toFixed(0)}%
                </span>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <ArcGauge value={s.battery.voltage_v} min={30} max={52}
                label="VOLTAGE" unit="V" color={battColor} size={90}
                thresholds={{ warn: 38, danger: 34, invert: true }} />
              <ArcGauge value={s.battery.current_a} min={0} max={60}
                label="CURRENT" unit="A" color="#f59e0b" size={90}
                thresholds={{ warn: 40, danger: 50 }} />
              <ArcGauge value={battPct} min={0} max={100}
                label="REMAINING" unit="%" color={battColor} size={90}
                thresholds={{ warn: 30, danger: 15, invert: true }} />
            </div>
          </GlassPanel>

          {/* GPS + Wind + Link */}
          <div className="grid grid-cols-2 gap-2">
            <GlassPanel padding="p-3">
              <span className="text-[8px] uppercase tracking-widest text-white/30">GPS</span>
              <div className="mt-2 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-mono text-white/40">Fix</span>
                  <span className="text-[10px] font-mono font-bold" style={{ color: gpsColor }}>
                    {GPS_FIX_LABELS[String(s.gps.fix_type)] ?? String(s.gps.fix_type)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-mono text-white/40">Sats</span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-mono font-bold" style={{ color: gpsColor }}>
                      {s.gps.num_satellites}
                    </span>
                    <SignalBars strength={Math.min(100, (s.gps.num_satellites / 15) * 100)} label="" />
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-mono text-white/40">HDOP</span>
                  <span className="text-[10px] font-mono text-white/60">{s.gps.hdop.toFixed(1)}</span>
                </div>
              </div>
            </GlassPanel>
            <GlassPanel padding="p-3">
              <span className="text-[8px] uppercase tracking-widest text-white/30">WIND</span>
              <div className="mt-2 flex items-center justify-around">
                <div className="relative w-12 h-12">
                  <svg width={48} height={48} viewBox="0 0 48 48">
                    <circle cx={24} cy={24} r={20} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
                    <g transform={`rotate(${s.wind.direction_deg}, 24, 24)`}>
                      <line x1={24} y1={6} x2={24} y2={18} stroke="#06b6d4" strokeWidth={2} strokeLinecap="round"
                        style={{ filter: 'drop-shadow(0 0 3px rgba(6,182,212,0.4))' }} />
                      <polygon points="24,4 21,12 27,12" fill="#06b6d4" />
                    </g>
                  </svg>
                </div>
                <div className="flex flex-col gap-1">
                  <StatCell label="SPEED" value={s.wind.speed_ms.toFixed(1)} unit="m/s" color="#06b6d4" />
                  <StatCell label="DIR" value={s.wind.direction_deg.toFixed(0)} unit="deg" />
                </div>
              </div>
            </GlassPanel>
          </div>
        </>
      )}

      {/* PX4 Parameter Map */}
      <GlassPanel padding="p-3">
        <div className="flex items-center justify-between">
          <span className="text-[8px] uppercase tracking-widest text-white/30">PARAMETER MAP</span>
          <button onClick={() => setShowParams(!showParams)} className="glass-button text-[9px] py-1 px-2 font-mono">
            {showParams ? 'HIDE' : `SHOW (${paramMap.length})`}
          </button>
        </div>
        {showParams && (
          <div className="mt-2 space-y-0.5 max-h-60 overflow-y-auto">
            {paramMap.map((m, i) => (
              <div key={i} className="flex items-center justify-between py-1 px-1.5 rounded border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                <div className="flex-1 min-w-0">
                  <span className="text-[9px] font-mono text-white/60">{m.px4_param}</span>
                  <span className="text-[8px] text-white/25 ml-2">{m.px4_description}</span>
                </div>
                <span className="text-[9px] font-mono text-white/35 flex-shrink-0 ml-2">
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
