import { useState, useEffect, useRef, useCallback, useId, useMemo } from 'react';
import { GlassPanel } from '../layout/GlassPanel';
import { chartStyles } from '../../theme/chartStyles';
import { colors } from '../../theme/tokens';
import { api, telemetryWsUrl } from '../../api/client';
import type {
  TelemetrySnapshot,
  ParamMapping,
  TelemetryLinkProfile,
  PreflightSummary,
} from '../../types/api';

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
  const [linkProfile, setLinkProfile] = useState<TelemetryLinkProfile>('default');
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [paramMap, setParamMap] = useState<ParamMapping[]>([]);
  const [showParams, setShowParams] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fcSyncStatus, setFcSyncStatus] = useState<string | null>(null);
  const [fcSyncing, setFcSyncing] = useState(false);
  const [fcParams, setFcParams] = useState<Record<string, Record<string, unknown>> | null>(null);
  const [msgRate, setMsgRate] = useState(0);
  const prevMsgCount = useRef(0);
  const prevMsgTime = useRef(Date.now());
  const pollRef = useRef<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const connectedRef = useRef(false);
  const startPollingRef = useRef<() => void>(() => {});

  useEffect(() => {
    connectedRef.current = connected;
  }, [connected]);

  const processSnapshot = useCallback((data: TelemetrySnapshot) => {
    setSnapshot(data);
    const isConn = data.connection?.connected ?? false;
    setConnected(isConn);
    if (isConn && data.connection?.link_profile) {
      setLinkProfile(data.connection.link_profile);
    }
    const now = Date.now();
    const dt = (now - prevMsgTime.current) / 1000;
    if (dt > 0.5) {
      const count = data.connection?.messages_received ?? 0;
      setMsgRate(Math.round((count - prevMsgCount.current) / dt));
      prevMsgCount.current = count;
      prevMsgTime.current = now;
    }
    // Push wind + ambient temperature upstream for the feasibility engine.
    // Temperature comes from the BATTERY_STATUS / envelope chain; when it's
    // absent we simply don't notify upstream (the old code fabricated 15 °C).
    if (onTelemetryUpdate && data.connection?.connected) {
      const wind = data.wind?.speed_ms;
      const temp = data.battery?.temperature_c;
      if (typeof wind === 'number' && typeof temp === 'number') {
        onTelemetryUpdate({ wind_speed_ms: wind, temperature_c: temp });
      }
    }
  }, [onTelemetryUpdate]);

  const startPolling = useCallback(() => {
    if (pollRef.current || wsRef.current) return;
    const intervalMs = linkProfile === 'low_bandwidth' ? 1000 : 500;
    const poll = async () => {
      try { const data = await api.telemetry.snapshot(); processSnapshot(data); setError(null); }
      catch (e) { setError(e instanceof Error ? e.message : 'Telemetry fetch failed'); }
    };
    poll();
    pollRef.current = window.setInterval(poll, intervalMs);
  }, [processSnapshot, linkProfile]);

  useEffect(() => {
    startPollingRef.current = startPolling;
  }, [startPolling]);

  const startWebSocket = useCallback(() => {
    if (wsRef.current) return;
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    try {
      // The backend always requires a token on the telemetry WS (JWT when
      // auth is on, a dev token otherwise). `telemetryWsUrl` attaches the
      // stored token so the live path doesn't silently fall back to polling.
      const ws = new WebSocket(telemetryWsUrl());
      ws.onopen = () => {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      };
      ws.onmessage = (event) => {
        try { processSnapshot(JSON.parse(event.data) as TelemetrySnapshot); setError(null); } catch {}
      };
      ws.onerror = () => {
        ws.close();
      };
      ws.onclose = () => {
        wsRef.current = null;
        setTimeout(() => {
          if (!wsRef.current) startPollingRef.current();
        }, 3000);
      };
      wsRef.current = ws;
    } catch {
      startPollingRef.current();
    }
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
      const res = await api.telemetry.connect(connectionAddr, { link_profile: linkProfile });
      if (ac.signal.aborted) return;
      if (res.link_profile === 'low_bandwidth' || res.link_profile === 'default') {
        setLinkProfile(res.link_profile);
      }
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
      if (s.connected) {
        const lp = s.link_profile ?? s.connection?.link_profile;
        if (lp === 'low_bandwidth' || lp === 'default') setLinkProfile(lp);
        setConnected(true);
        startWebSocket();
      }
    }).catch(() => {});
    api.telemetry.paramMap().then(d => setParamMap(d.mappings || [])).catch(() => {});
    return () => {
      stopAll();
    };
  }, [startWebSocket, stopAll]);

  useEffect(() => {
    const handleUnload = () => { api.telemetry.disconnect().catch(() => {}); };
    window.addEventListener('beforeunload', handleUnload);
    return () => window.removeEventListener('beforeunload', handleUnload);
  }, []);

  const s = snapshot;
  const battPct = s?.battery.remaining_pct ?? 0;
  const battColor = battPct > 50 ? colors.status.success : battPct > 20 ? colors.status.warning : colors.status.danger;
  const gpsColor = (s?.gps.num_satellites ?? 0) >= 10 ? colors.status.success
    : (s?.gps.num_satellites ?? 0) >= 6 ? colors.status.warning : colors.status.danger;
  // Flight-mode string. PX4's `MANUAL`, `AUTO.MISSION`, etc. are passed through
  // verbatim (backend already decodes them); the ArduPilot table is a legacy
  // fallback for bench tests that still send numeric custom_mode.
  const flightMode = s?.status.flight_mode
    ? ARDUPILOT_MODES[s.status.flight_mode] ?? s.status.flight_mode
    : 'UNKNOWN';
  const vtolState = s?.status.vtol_state;
  const landedState = s?.status.landed_state;
  const autopilot = s?.connection?.autopilot ?? 'unknown';
  const uptime = s?.connection?.uptime_s ?? 0;
  const uptimeStr = uptime > 0 ? `${Math.floor(uptime / 60)}:${String(Math.floor(uptime % 60)).padStart(2, '0')}` : '--:--';
  const heartbeatAge = s?.connection?.heartbeat_age_s ?? null;
  const preArm = s?.pre_arm_messages ?? [];
  const sensorHealth = s?.health?.sensor_health ?? {};
  const sensorEnabled = s?.health?.sensor_enabled ?? {};

  // Coerce possibly-null scalars to displayable numbers for the HUD.
  const num = (v: number | null | undefined, fb = 0) => (typeof v === 'number' && Number.isFinite(v) ? v : fb);

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
        {connected && linkProfile === 'low_bandwidth' && (
          <div className="flex items-center gap-2 text-[9px] font-mono text-amber-400/70">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400/60" />
            LoRa mode — low-bandwidth rates auto-selected for serial link
          </div>
        )}
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
              <div className="flex flex-wrap items-center justify-between gap-3">
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
                  {vtolState && (
                    <VtolBadge state={vtolState} />
                  )}
                  {landedState && landedState !== 'UNDEFINED' && (
                    <span className="text-[8px] font-mono tracking-widest text-white/40 uppercase">
                      {landedState.replace('_', ' ')}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[8px] font-mono text-white/30 uppercase tracking-widest">
                    {autopilot}
                  </span>
                  <div className="px-3 py-1 rounded-md bg-white/[0.06] border border-white/[0.08]">
                    <span className="text-xs font-mono font-bold tracking-wider text-white/90"
                      style={{ textShadow: '0 0 10px rgba(255,255,255,0.15)' }}>
                      {flightMode}
                    </span>
                  </div>
                </div>
              </div>
              {heartbeatAge != null && heartbeatAge > 2 && (
                <div className="mt-2 text-[9px] font-mono text-amber-400/70">
                  Heartbeat age {heartbeatAge.toFixed(1)}s — link may be degraded
                </div>
              )}
            </GlassPanel>
          </div>

          {/* HUD Row: Attitude + Heading + Key Stats */}
          <div className="flex gap-2.5">
            <GlassPanel padding="p-3" className="flex flex-col items-center justify-center">
              <span className="text-[8px] uppercase tracking-widest text-white/30 mb-1">ATTITUDE</span>
              <AttitudeIndicator roll={num(s.attitude.roll_deg)} pitch={num(s.attitude.pitch_deg)} />
            </GlassPanel>
            <GlassPanel padding="p-3" className="flex flex-col items-center justify-center">
              <span className="text-[8px] uppercase tracking-widest text-white/30 mb-1">HEADING</span>
              <HeadingCompass heading={((num(s.attitude.yaw_deg) % 360) + 360) % 360} />
            </GlassPanel>
            <GlassPanel padding="p-3" className="flex-1">
              <span className="text-[8px] uppercase tracking-widest text-white/30">POSITION</span>
              <div className="mt-2 space-y-1.5">
                <StatCell
                  label="LATITUDE"
                  value={s.position.latitude_deg != null ? formatCoord(s.position.latitude_deg, true) : '—'}
                />
                <StatCell
                  label="LONGITUDE"
                  value={s.position.longitude_deg != null ? formatCoord(s.position.longitude_deg, false) : '—'}
                />
                <div className="grid grid-cols-2 gap-1.5">
                  <StatCell label="ALT MSL" value={s.position.absolute_altitude_m != null ? s.position.absolute_altitude_m.toFixed(1) : '—'} unit="m" />
                  <StatCell
                    label="ALT AGL"
                    value={s.position.relative_altitude_m != null ? s.position.relative_altitude_m.toFixed(1) : '—'}
                    unit="m"
                    color={num(s.position.relative_altitude_m) > 0 ? '#60a5fa' : undefined}
                  />
                </div>
              </div>
            </GlassPanel>
          </div>

          {/* Velocity Gauges */}
          <GlassPanel padding="p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[8px] uppercase tracking-widest text-white/30">VELOCITY</span>
              <span className="text-[9px] font-mono text-white/25">
                N:{num(s.velocity.velocity_north_ms).toFixed(1)} E:{num(s.velocity.velocity_east_ms).toFixed(1)} D:{num(s.velocity.velocity_down_ms).toFixed(1)}
              </span>
            </div>
            <div className="flex items-center justify-around">
              <ArcGauge value={num(s.velocity.groundspeed_ms)} min={0} max={40}
                label="GND SPEED" unit="m/s" color="#ffffff" size={100} />
              <ArcGauge value={num(s.velocity.airspeed_ms)} min={0} max={40}
                label="AIR SPEED" unit="m/s" color="#06b6d4" size={100} />
              <ArcGauge value={num(s.velocity.climb_rate_ms)} min={-10} max={10}
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
              <ArcGauge value={num(s.battery.voltage_v)} min={30} max={52}
                label="VOLTAGE" unit="V" color={battColor} size={90}
                thresholds={{ warn: 38, danger: 34, invert: true }} />
              <ArcGauge value={num(s.battery.current_a)} min={0} max={60}
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
                    {s.gps.fix_type ? (GPS_FIX_LABELS[String(s.gps.fix_type)] ?? String(s.gps.fix_type)) : '—'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-mono text-white/40">Sats</span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-mono font-bold" style={{ color: gpsColor }}>
                      {s.gps.num_satellites ?? '—'}
                    </span>
                    <SignalBars strength={Math.min(100, (num(s.gps.num_satellites) / 15) * 100)} label="" />
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-mono text-white/40">HDOP</span>
                  <span className="text-[10px] font-mono text-white/60">
                    {s.gps.hdop != null ? s.gps.hdop.toFixed(2) : '—'}
                  </span>
                </div>
              </div>
            </GlassPanel>
            <GlassPanel padding="p-3">
              <span className="text-[8px] uppercase tracking-widest text-white/30">WIND</span>
              <div className="mt-2 flex items-center justify-around">
                <div className="relative w-12 h-12">
                  <svg width={48} height={48} viewBox="0 0 48 48">
                    <circle cx={24} cy={24} r={20} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
                    <g transform={`rotate(${num(s.wind.direction_deg)}, 24, 24)`}>
                      <line x1={24} y1={6} x2={24} y2={18} stroke="#06b6d4" strokeWidth={2} strokeLinecap="round"
                        style={{ filter: 'drop-shadow(0 0 3px rgba(6,182,212,0.4))' }} />
                      <polygon points="24,4 21,12 27,12" fill="#06b6d4" />
                    </g>
                  </svg>
                </div>
                <div className="flex flex-col gap-1">
                  <StatCell
                    label="SPEED"
                    value={s.wind.speed_ms != null ? s.wind.speed_ms.toFixed(1) : '—'}
                    unit="m/s"
                    color="#06b6d4"
                  />
                  <StatCell
                    label="DIR"
                    value={s.wind.direction_deg != null ? s.wind.direction_deg.toFixed(0) : '—'}
                    unit="deg"
                  />
                </div>
              </div>
            </GlassPanel>
          </div>

          <SensorHealthPanel
            present={s.health?.sensor_present ?? {}}
            enabled={sensorEnabled}
            health={sensorHealth}
          />

          <PreArmMessagesPanel messages={preArm} />

          <PreflightChecklistPanel connected={connected} />
        </>
      )}

      {/* PX4 Parameter Map + FC Sync */}
      <GlassPanel padding="p-3">
        <div className="flex items-center justify-between">
          <span className="text-[8px] uppercase tracking-widest text-white/30">FC PARAMETERS</span>
          <div className="flex items-center gap-1.5">
            {connected && (
              <>
                <button
                  disabled={fcSyncing}
                  onClick={async () => {
                    setFcSyncing(true); setFcSyncStatus('Reading FC params…');
                    try {
                      const res = await api.telemetry.readParamsFromFC();
                      setFcParams(res.twin_params);
                      setFcSyncStatus(`Read ${res.fc_param_count} params — ${res.subsystems_affected.join(', ')}`);
                      setError(null);
                    } catch (e) {
                      setFcSyncStatus(null);
                      setError(e instanceof Error ? e.message : 'Read failed');
                    } finally { setFcSyncing(false); }
                  }}
                  className="glass-button text-[8px] py-0.5 px-2 font-mono text-cyan-400 border-cyan-500/20 disabled:opacity-40"
                >
                  {fcSyncing ? '…' : 'READ FC'}
                </button>
                <button
                  disabled={fcSyncing}
                  onClick={async () => {
                    setFcSyncing(true); setFcSyncStatus('Writing params to FC…');
                    try {
                      const res = await api.telemetry.syncParamsToFC(fcParams ?? {});
                      setFcSyncStatus(`Synced ${res.synced} params to FC` + (res.failed > 0 ? ` (${res.failed} failed)` : ''));
                      setError(null);
                    } catch (e) {
                      setFcSyncStatus(null);
                      setError(e instanceof Error ? e.message : 'Sync failed');
                    } finally { setFcSyncing(false); }
                  }}
                  className="glass-button text-[8px] py-0.5 px-2 font-mono text-amber-400 border-amber-500/20 disabled:opacity-40"
                >
                  {fcSyncing ? '…' : 'SYNC TO FC'}
                </button>
              </>
            )}
            <button onClick={() => setShowParams(!showParams)} className="glass-button text-[9px] py-1 px-2 font-mono">
              {showParams ? 'HIDE' : `SHOW (${paramMap.length})`}
            </button>
          </div>
        </div>
        {fcSyncStatus && (
          <div className="mt-1.5 p-1.5 rounded-lg bg-white/[0.03] border border-white/[0.06] text-[9px] font-mono text-white/50">
            {fcSyncStatus}
          </div>
        )}
        {fcParams && (
          <div className="mt-1.5 space-y-0.5 max-h-40 overflow-y-auto">
            {Object.entries(fcParams).map(([subsystem, params]) => (
              <div key={subsystem}>
                <span className="text-[8px] uppercase tracking-wider text-white/25">{subsystem}</span>
                {Object.entries(params as Record<string, unknown>).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between py-0.5 px-1.5">
                    <span className="text-[9px] font-mono text-white/50">{k}</span>
                    <span className="text-[9px] font-mono text-emerald-400/70">{typeof v === 'number' ? v.toFixed(3) : String(v)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
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

// ─── VTOL state badge ────────────────────────────────────────────────────────

function VtolBadge({ state }: { state: NonNullable<TelemetrySnapshot['status']['vtol_state']> }) {
  if (state === 'UNDEFINED') return null;
  const config: Record<string, { label: string; color: string; bg: string; border: string }> = {
    MC: {
      label: 'MULTIROTOR',
      color: '#60a5fa',
      bg: 'rgba(96,165,250,0.12)',
      border: 'rgba(96,165,250,0.30)',
    },
    FW: {
      label: 'FIXED-WING',
      color: '#a78bfa',
      bg: 'rgba(167,139,250,0.12)',
      border: 'rgba(167,139,250,0.30)',
    },
    TRANSITION_TO_FW: {
      label: 'TRANS → FW',
      color: '#f59e0b',
      bg: 'rgba(245,158,11,0.12)',
      border: 'rgba(245,158,11,0.35)',
    },
    TRANSITION_TO_MC: {
      label: 'TRANS → MC',
      color: '#f59e0b',
      bg: 'rgba(245,158,11,0.12)',
      border: 'rgba(245,158,11,0.35)',
    },
  };
  const cfg = config[state];
  if (!cfg) return null;
  return (
    <div
      className="px-2 py-0.5 rounded-md text-[8px] font-mono font-bold tracking-widest uppercase"
      style={{
        background: cfg.bg,
        border: `1px solid ${cfg.border}`,
        color: cfg.color,
        boxShadow: `0 0 6px ${cfg.color}30`,
      }}
    >
      {cfg.label}
    </div>
  );
}

// ─── Sensor health grid ──────────────────────────────────────────────────────

const SENSOR_DISPLAY_ORDER: [key: string, label: string][] = [
  ['gyro', 'Gyro'],
  ['accel', 'Accel'],
  ['mag', 'Mag'],
  ['abs_pressure', 'Baro'],
  ['diff_pressure', 'Airspeed'],
  ['gps', 'GPS'],
  ['ahrs', 'AHRS'],
  ['xy_position_control', 'XY Ctrl'],
  ['z_altitude_control', 'Alt Ctrl'],
  ['attitude_stabilization', 'Att Stab'],
  ['motor_outputs', 'Motors'],
  ['rc_receiver', 'RC'],
  ['battery', 'Battery'],
  ['logging', 'Log'],
  ['prearm_check', 'Pre-arm'],
];

function SensorHealthPanel({
  present,
  enabled,
  health,
}: {
  present: Record<string, boolean>;
  enabled: Record<string, boolean>;
  health: Record<string, boolean>;
}) {
  const hasAnyEnabled = Object.values(enabled).some(Boolean);
  if (!hasAnyEnabled) return null;
  return (
    <GlassPanel padding="p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[8px] uppercase tracking-widest text-white/30">SENSOR HEALTH</span>
        <span className="text-[8px] font-mono text-white/25">SYS_STATUS bitmask</span>
      </div>
      <div className="grid grid-cols-5 gap-1.5">
        {SENSOR_DISPLAY_ORDER.filter(([key]) => present[key] || enabled[key]).map(([key, label]) => {
          const isEnabled = !!enabled[key];
          const isHealthy = !!health[key];
          const status = !isEnabled ? 'off' : isHealthy ? 'ok' : 'fault';
          const color =
            status === 'off'
              ? 'rgba(255,255,255,0.15)'
              : status === 'ok'
              ? '#10b981'
              : '#ef4444';
          const ring =
            status === 'off'
              ? 'rgba(255,255,255,0.06)'
              : status === 'ok'
              ? 'rgba(16,185,129,0.25)'
              : 'rgba(239,68,68,0.35)';
          return (
            <div
              key={key}
              className="flex items-center gap-1.5 px-1.5 py-1 rounded bg-white/[0.02] border"
              style={{ borderColor: ring }}
              title={`${key}: ${status}`}
            >
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{
                  backgroundColor: color,
                  boxShadow: status !== 'off' ? `0 0 5px ${color}80` : undefined,
                }}
              />
              <span
                className={`text-[9px] font-mono ${
                  status === 'fault' ? 'text-red-400' : status === 'ok' ? 'text-white/65' : 'text-white/30'
                }`}
              >
                {label}
              </span>
            </div>
          );
        })}
      </div>
    </GlassPanel>
  );
}

// ─── Pre-arm STATUSTEXT stream ───────────────────────────────────────────────

function PreArmMessagesPanel({ messages }: { messages: string[] }) {
  if (messages.length === 0) return null;
  return (
    <GlassPanel padding="p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[8px] uppercase tracking-widest text-white/30">FC MESSAGES</span>
        <span className="text-[8px] font-mono text-white/25">most recent · {messages.length}</span>
      </div>
      <div className="space-y-1 max-h-36 overflow-y-auto">
        {messages.map((msg, i) => {
          // Format: "[severity] text". severity 0-3 is critical/error/warning.
          const match = msg.match(/^\[(\d+)\]\s*(.*)$/);
          const sev = match ? Number(match[1]) : 6;
          const body = match ? match[2] : msg;
          const color = sev <= 3 ? '#ef4444' : sev <= 4 ? '#f59e0b' : 'rgba(255,255,255,0.55)';
          return (
            <div key={`${i}-${msg}`} className="flex items-start gap-2 text-[10px] font-mono">
              <span
                className="w-1 h-1 rounded-full flex-shrink-0 mt-1.5"
                style={{ backgroundColor: color, boxShadow: `0 0 4px ${color}80` }}
              />
              <span style={{ color }}>{body}</span>
            </div>
          );
        })}
      </div>
    </GlassPanel>
  );
}

// ─── Pre-flight checklist (uses /telemetry/preflight) ────────────────────────

function PreflightChecklistPanel({ connected }: { connected: boolean }) {
  const [summary, setSummary] = useState<PreflightSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!connected) {
      setSummary(null);
      return;
    }
    let cancelled = false;
    const poll = async () => {
      setLoading(true);
      try {
        const res = await api.telemetry.preflight();
        if (!cancelled) setSummary(res);
      } catch {
        /* banner covers the error */
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    poll();
    const id = window.setInterval(poll, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [connected]);

  if (!connected) return null;
  const ready = summary?.ready ?? false;
  const checks = summary?.checks ?? [];
  const headline = !summary
    ? 'Checking…'
    : ready
    ? 'Ready to arm'
    : `Blocked: ${summary.blocking_failures.join(', ') || 'pending'}`;
  const headlineColor = !summary
    ? 'text-white/40'
    : ready
    ? 'text-emerald-400'
    : 'text-red-400';

  return (
    <GlassPanel padding="p-3">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center justify-between w-full outline-none focus-visible:ring-2 focus-visible:ring-gorzen-500/30 rounded"
      >
        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full ${loading ? 'animate-pulse' : ''}`}
            style={{
              backgroundColor: !summary
                ? 'rgba(255,255,255,0.25)'
                : ready
                ? '#10b981'
                : '#ef4444',
              boxShadow: summary
                ? `0 0 6px ${ready ? 'rgba(16,185,129,0.55)' : 'rgba(239,68,68,0.55)'}`
                : undefined,
            }}
          />
          <span className="text-[9px] font-mono uppercase tracking-wider text-white/50">
            PRE-FLIGHT
          </span>
          <span className={`text-[10px] font-mono font-semibold ${headlineColor}`}>
            {headline}
          </span>
        </div>
        <span className="text-[9px] font-mono text-white/30">
          {expanded ? '▾' : '▸'}
        </span>
      </button>
      {expanded && checks.length > 0 && (
        <div className="mt-2 space-y-1 border-t border-white/[0.05] pt-2">
          {checks.map((c) => (
            <div key={c.name} className="flex items-start gap-2 text-[10px] font-mono">
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1"
                style={{
                  backgroundColor: c.passed ? '#10b981' : c.blocking ? '#ef4444' : '#f59e0b',
                }}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={c.passed ? 'text-white/70' : c.blocking ? 'text-red-400' : 'text-amber-400'}>
                    {c.name}
                  </span>
                  {!c.passed && !c.blocking && (
                    <span className="text-[8px] uppercase text-amber-400/70 tracking-widest">warn</span>
                  )}
                </div>
                <div className="text-white/40 text-[9px] truncate">{c.detail}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </GlassPanel>
  );
}
