import { useState, useRef, useEffect, useCallback } from 'react';
import { GlassPanel } from '../layout/GlassPanel';
import { chartStyles } from '../../theme/chartStyles';
import { api } from '../../api/client';
import type { FcLogEntry } from '../../types/api';

interface LogSummary {
  filename: string;
  duration_s: number;
  topics: string[];
  parameter_count: number;
  message_count: number;
  vehicle_uuid: string;
  software_version: string;
}

interface VibrationAxis {
  peak_to_peak_ms2: number;
  rms_ms2: number;
  std_ms2: number;
  pass: boolean;
}

interface VibrationResult {
  available: boolean;
  reason?: string;
  axes?: Record<string, VibrationAxis>;
  threshold_ms2?: number;
  overall_pass?: boolean;
}

interface QualityResult {
  battery?: {
    start_v: number;
    end_v: number;
    min_v: number;
    max_v: number;
    sag_v: number;
    avg_current_a?: number;
    max_current_a?: number;
    total_discharged_mah?: number;
  };
  duration_s?: number;
  airspeed?: { mean_ms: number; max_ms: number; std_ms: number };
  estimator?: { mean_horiz_accuracy_m?: number; mean_vert_accuracy_m?: number };
}

interface CalibrationData {
  topics_found: string[];
  data: Record<string, Record<string, number[]>>;
  px4_parameters: Record<string, any>;
  stats?: {
    battery_start_v: number;
    battery_end_v: number;
    battery_min_v: number;
    flight_duration_s: number;
  };
}

interface AnalysisResult {
  summary: LogSummary;
  calibration: CalibrationData;
  vibration: VibrationResult;
  quality: QualityResult;
  log_id?: string | null;
}

interface LogRecord {
  id: string;
  filename?: string;
  file_path?: string;
  source_format: string;
  duration_s?: number;
  uploaded_at?: string;
  log_metadata?: Record<string, any>;
}

const TOPIC_COLORS: Record<string, string> = {
  battery_status: '#f59e0b',
  vehicle_attitude: '#3b82f6',
  vehicle_local_position: '#10b981',
  vehicle_global_position: '#06b6d4',
  airspeed_validated: '#8b5cf6',
  wind_estimate: '#ec4899',
  sensor_combined: '#64748b',
  vehicle_air_data: '#14b8a6',
  actuator_outputs: '#f97316',
  estimator_status: '#6366f1',
};

function MiniChart({ timestamps, values, color, label, unit, height = 60 }: {
  timestamps: number[]; values: number[]; color: string; label: string; unit: string; height?: number;
}) {
  if (!timestamps?.length || !values?.length) return null;
  const w = 300, h = height;
  const pad = { top: 4, right: 4, bottom: 4, left: 4 };
  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;

  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const rangeV = maxV - minV || 1;
  const maxT = timestamps[timestamps.length - 1] || 1;

  const points = timestamps.map((t, i) => {
    const x = pad.left + (t / maxT) * plotW;
    const y = pad.top + plotH - ((values[i] - minV) / rangeV) * plotH;
    return `${x},${y}`;
  });

  const linePath = `M${points.join(' L')}`;
  const areaPath = `${linePath} L${pad.left + plotW},${pad.top + plotH} L${pad.left},${pad.top + plotH} Z`;

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
          <span className="text-[10px] text-white/60 font-medium">{label}</span>
        </div>
        <div className="text-[10px] font-mono text-white/50">
          {minV.toFixed(1)} — {maxV.toFixed(1)} {unit}
        </div>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ maxHeight: height }}>
        <path d={areaPath} fill={`${color}15`} />
        <path d={linePath} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

export function FlightLogAnalyzer() {
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previousLogs, setPreviousLogs] = useState<LogRecord[]>([]);
  const [selectedTopics, setSelectedTopics] = useState<Set<string>>(new Set(['battery_status', 'vehicle_local_position', 'airspeed_validated']));
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.telemetry.listLogs()
      .then((logs) => setPreviousLogs(logs as unknown as LogRecord[]))
      .catch(() => {});
  }, []);

  const handleUpload = async (file: File) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.telemetry.analyzeLog(file);
      setResult(data as unknown as AnalysisResult);
      api.telemetry.listLogs()
        .then((logs) => setPreviousLogs(logs as unknown as LogRecord[]))
        .catch(() => {});
    } catch (e: any) {
      setError(e.message || 'Upload failed');
    } finally {
      setLoading(false);
    }
  };

  const toggleTopic = (topic: string) => {
    setSelectedTopics(prev => {
      const next = new Set(prev);
      if (next.has(topic)) next.delete(topic); else next.add(topic);
      return next;
    });
  };

  const formatDuration = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}m ${sec}s`;
  };

  const summary = result?.summary;
  const calibration = result?.calibration;
  const vibration = result?.vibration;
  const quality = result?.quality;

  return (
    <div className="h-full overflow-y-auto space-y-3 p-3">
      <FcLogsPanel onDownloaded={() => api.telemetry.listLogs().then((logs) => setPreviousLogs(logs as unknown as LogRecord[])).catch(() => {})} />

      {/* Upload */}
      <GlassPanel padding="p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className={chartStyles.title}>Flight Log Analyzer</h2>
          <span className="text-[10px] text-white/35">PX4 .ulg format</span>
        </div>
        <div
          className="border-2 border-dashed border-white/10 rounded-xl p-6 text-center cursor-pointer hover:border-gorzen-500/30 hover:bg-gorzen-500/[0.03] transition-all"
          onClick={() => fileRef.current?.click()}
          onDragOver={e => { e.preventDefault(); e.stopPropagation(); }}
          onDrop={e => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file?.name.endsWith('.ulg')) handleUpload(file);
          }}
        >
          <input
            ref={fileRef} type="file" accept=".ulg" aria-label="Upload PX4 flight log" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(f); }}
          />
          {loading ? (
            <div className="text-white/50 text-sm">Analyzing flight log...</div>
          ) : (
            <>
              <div className="text-white/50 text-sm mb-1">Drop .ulg file here or click to browse</div>
              <div className="text-white/30 text-[10px]">PX4 uLog flight recording — single-pass analysis</div>
            </>
          )}
        </div>
        {error && <div className="mt-2 text-xs text-red-400">{error}</div>}
      </GlassPanel>

      {/* Previous Logs */}
      {previousLogs.length > 0 && !summary && (
        <GlassPanel padding="p-4">
          <h3 className={`${chartStyles.title} mb-3`}>Previous Logs</h3>
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {previousLogs.map((log) => (
              <div key={log.id} className="flex items-center justify-between py-1.5 border-b border-white/[0.04] last:border-0">
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] font-mono text-white/70 truncate">{log.file_path || log.id.slice(0, 12)}</div>
                  <div className="text-[9px] text-white/35">
                    {log.uploaded_at ? new Date(log.uploaded_at).toLocaleDateString() : ''}
                    {log.log_metadata?.duration_s ? ` — ${formatDuration(log.log_metadata.duration_s)}` : ''}
                  </div>
                </div>
                {log.log_metadata?.vibration_pass != null && (
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${log.log_metadata.vibration_pass ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                    {log.log_metadata.vibration_pass ? 'PASS' : 'VIB'}
                  </span>
                )}
              </div>
            ))}
          </div>
        </GlassPanel>
      )}

      {summary && (
        <>
          {/* Log Summary */}
          <GlassPanel padding="p-4">
            <h3 className={chartStyles.title}>Log Summary</h3>
            <div className="grid grid-cols-3 gap-4 mt-3">
              <div>
                <div className={chartStyles.label}>Duration</div>
                <div className="text-lg font-bold font-mono text-white/90">{formatDuration(summary.duration_s)}</div>
              </div>
              <div>
                <div className={chartStyles.label}>Messages</div>
                <div className="text-lg font-bold font-mono text-white/90">{summary.message_count.toLocaleString()}</div>
              </div>
              <div>
                <div className={chartStyles.label}>Parameters</div>
                <div className="text-lg font-bold font-mono text-white/90">{summary.parameter_count}</div>
              </div>
            </div>
            <div className="mt-3 pt-3 border-t border-white/[0.06] grid grid-cols-2 gap-2 text-[10px]">
              <div><span className="text-white/40">File:</span> <span className="text-white/70 font-mono">{summary.filename}</span></div>
              <div><span className="text-white/40">Topics:</span> <span className="text-white/70 font-mono">{summary.topics.length}</span></div>
              {summary.software_version && <div><span className="text-white/40">PX4:</span> <span className="text-white/70 font-mono">{summary.software_version}</span></div>}
              {summary.vehicle_uuid && <div><span className="text-white/40">UUID:</span> <span className="text-white/70 font-mono">{summary.vehicle_uuid.slice(0, 12)}</span></div>}
              {result?.log_id && <div><span className="text-white/40">Log ID:</span> <span className="text-white/70 font-mono">{result.log_id.slice(0, 12)}</span></div>}
            </div>
          </GlassPanel>

          {/* Vibration Analysis */}
          {vibration?.available && vibration.axes && (
            <GlassPanel padding="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className={chartStyles.title}>Vibration Analysis</h3>
                <span className={`text-[9px] font-bold px-2 py-0.5 rounded ${vibration.overall_pass ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                  {vibration.overall_pass ? 'PASS' : 'FAIL'}
                </span>
              </div>
              <div className="text-[9px] text-white/35 mb-3">
                Threshold: {vibration.threshold_ms2} m/s² peak-to-peak (PX4 recommended)
              </div>
              <div className="grid grid-cols-3 gap-3">
                {Object.entries(vibration.axes).map(([axis, data]) => (
                  <div key={axis} className="bg-white/[0.04] rounded-lg p-3 border border-white/[0.05]">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-bold text-white/60 uppercase">{axis}-axis</span>
                      <span className={`text-[9px] font-bold ${data.pass ? 'text-emerald-400' : 'text-red-400'}`}>
                        {data.pass ? 'OK' : 'HIGH'}
                      </span>
                    </div>
                    <div className="text-sm font-mono font-bold" style={{ color: data.pass ? '#10b981' : '#ef4444' }}>
                      {data.peak_to_peak_ms2.toFixed(2)}
                    </div>
                    <div className="text-[9px] text-white/30">m/s² p2p</div>
                    <div className="text-[9px] text-white/35 mt-1">
                      RMS: {data.rms_ms2.toFixed(2)} | σ: {data.std_ms2.toFixed(3)}
                    </div>
                  </div>
                ))}
              </div>
            </GlassPanel>
          )}

          {/* Flight Quality */}
          {quality && (quality.battery || quality.airspeed || quality.estimator) && (
            <GlassPanel padding="p-4">
              <h3 className={`${chartStyles.title} mb-3`}>Flight Quality</h3>
              <div className="grid grid-cols-2 gap-3">
                {quality.battery && (
                  <div className="bg-white/[0.04] rounded-lg p-3 border border-white/[0.05]">
                    <div className="text-[9px] font-semibold uppercase tracking-wider text-amber-400/70 mb-2">Battery</div>
                    <div className="space-y-1 text-[10px]">
                      <div className="flex justify-between">
                        <span className="text-white/40">Start → End</span>
                        <span className="font-mono text-white/70">{quality.battery.start_v}V → {quality.battery.end_v}V</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-white/40">Sag</span>
                        <span className="font-mono" style={{ color: quality.battery.sag_v < 2 ? '#10b981' : '#f59e0b' }}>{quality.battery.sag_v}V</span>
                      </div>
                      {quality.battery.total_discharged_mah != null && (
                        <div className="flex justify-between">
                          <span className="text-white/40">Discharged</span>
                          <span className="font-mono text-white/70">{quality.battery.total_discharged_mah} mAh</span>
                        </div>
                      )}
                      {quality.battery.max_current_a != null && (
                        <div className="flex justify-between">
                          <span className="text-white/40">Max Current</span>
                          <span className="font-mono text-white/70">{quality.battery.max_current_a}A</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {quality.airspeed && (
                  <div className="bg-white/[0.04] rounded-lg p-3 border border-white/[0.05]">
                    <div className="text-[9px] font-semibold uppercase tracking-wider text-blue-400/70 mb-2">Airspeed</div>
                    <div className="space-y-1 text-[10px]">
                      <div className="flex justify-between">
                        <span className="text-white/40">Mean</span>
                        <span className="font-mono text-white/70">{quality.airspeed.mean_ms} m/s</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-white/40">Max</span>
                        <span className="font-mono text-white/70">{quality.airspeed.max_ms} m/s</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-white/40">Std Dev</span>
                        <span className="font-mono text-white/70">{quality.airspeed.std_ms} m/s</span>
                      </div>
                    </div>
                  </div>
                )}
                {quality.estimator && (
                  <div className="bg-white/[0.04] rounded-lg p-3 border border-white/[0.05] col-span-2">
                    <div className="text-[9px] font-semibold uppercase tracking-wider text-purple-400/70 mb-2">Position Accuracy</div>
                    <div className="flex gap-6 text-[10px]">
                      {quality.estimator.mean_horiz_accuracy_m != null && (
                        <div>
                          <span className="text-white/40">Horizontal: </span>
                          <span className="font-mono text-white/70">{quality.estimator.mean_horiz_accuracy_m}m</span>
                        </div>
                      )}
                      {quality.estimator.mean_vert_accuracy_m != null && (
                        <div>
                          <span className="text-white/40">Vertical: </span>
                          <span className="font-mono text-white/70">{quality.estimator.mean_vert_accuracy_m}m</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </GlassPanel>
          )}

          {/* Topic Selector */}
          <GlassPanel padding="p-4">
            <h3 className={`${chartStyles.title} mb-3`}>Data Channels</h3>
            <div className="flex flex-wrap gap-1.5">
              {(calibration?.topics_found || []).map(topic => {
                const active = selectedTopics.has(topic);
                const color = TOPIC_COLORS[topic] || '#64748b';
                return (
                  <button
                    key={topic}
                    onClick={() => toggleTopic(topic)}
                    className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] font-medium transition-all border"
                    style={{
                      borderColor: active ? color + '40' : 'rgba(255,255,255,0.06)',
                      background: active ? color + '15' : 'transparent',
                      color: active ? color : 'rgba(255,255,255,0.4)',
                    }}
                  >
                    <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color, opacity: active ? 1 : 0.3 }} />
                    {topic.replace(/_/g, ' ')}
                  </button>
                );
              })}
            </div>
          </GlassPanel>

          {/* Timeseries Charts */}
          {calibration && Array.from(selectedTopics).map(topic => {
            const topicData = calibration.data[topic];
            if (!topicData) return null;
            const timestamps = topicData.timestamps_s;
            if (!timestamps) return null;
            const color = TOPIC_COLORS[topic] || '#64748b';
            const fields = Object.keys(topicData).filter(k => k !== 'timestamps_s');

            return (
              <GlassPanel key={topic} padding="p-4">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                  <h3 className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: color + 'cc' }}>
                    {topic.replace(/_/g, ' ')}
                  </h3>
                </div>
                <div className="space-y-3">
                  {fields.map(field => (
                    <MiniChart
                      key={field}
                      timestamps={timestamps}
                      values={topicData[field]}
                      color={color}
                      label={field.replace(/_/g, ' ')}
                      unit=""
                    />
                  ))}
                </div>
              </GlassPanel>
            );
          })}

          {/* PX4 Parameters from Log */}
          {calibration?.px4_parameters && Object.keys(calibration.px4_parameters).length > 0 && (
            <GlassPanel padding="p-4">
              <h3 className={`${chartStyles.title} mb-3`}>PX4 Parameters (from log)</h3>
              <div className="max-h-48 overflow-y-auto space-y-0.5">
                {Object.entries(calibration.px4_parameters).slice(0, 50).map(([key, val]) => (
                  <div key={key} className="flex items-center justify-between py-0.5">
                    <span className="text-[10px] font-mono text-white/50">{key}</span>
                    <span className="text-[10px] font-mono text-white/80">{typeof val === 'number' ? val.toFixed(4) : String(val)}</span>
                  </div>
                ))}
                {Object.keys(calibration.px4_parameters).length > 50 && (
                  <div className="text-[10px] text-white/30 pt-1">... and {Object.keys(calibration.px4_parameters).length - 50} more</div>
                )}
              </div>
            </GlassPanel>
          )}
        </>
      )}
    </div>
  );
}

// ─── FC on-board log manager ─────────────────────────────────────────────────

function FcLogsPanel({ onDownloaded }: { onDownloaded: () => void }) {
  const [logs, setLogs] = useState<FcLogEntry[] | null>(null);
  const [listing, setListing] = useState(false);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [erasing, setErasing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setListing(true);
    setError(null);
    try {
      const res = await api.telemetry.listLogsFromFc();
      setLogs(res.logs);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to list FC logs');
      setLogs([]);
    } finally {
      setListing(false);
    }
  }, []);

  const download = async (log: FcLogEntry) => {
    setDownloadingId(log.id);
    setError(null);
    try {
      const res = await api.telemetry.downloadLogFromFc(log.id);
      // Decode base64 -> Blob and trigger a browser download.
      const binary = atob(res.base64_data);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const blob = new Blob([bytes], { type: 'application/octet-stream' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `fc_log_${log.id}.ulg`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      onDownloaded();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed');
    } finally {
      setDownloadingId(null);
    }
  };

  const erase = async () => {
    if (!window.confirm('Erase ALL on-board logs on the FC? This cannot be undone.')) return;
    setErasing(true);
    setError(null);
    try {
      await api.telemetry.eraseFcLogs();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erase failed');
    } finally {
      setErasing(false);
    }
  };

  const totalBytes = logs?.reduce((sum, l) => sum + l.size_bytes, 0) ?? 0;

  return (
    <GlassPanel padding="p-4">
      <div className="flex items-center justify-between mb-2.5">
        <h3 className={chartStyles.title}>On-Board Logs</h3>
        <div className="flex items-center gap-1.5">
          <button
            onClick={refresh}
            disabled={listing}
            className="glass-button text-[10px] py-1 px-2.5 font-mono tracking-widest disabled:opacity-40"
          >
            {listing ? 'LISTING…' : 'LIST'}
          </button>
          <button
            onClick={erase}
            disabled={erasing || !logs || logs.length === 0}
            className="glass-button text-[10px] py-1 px-2.5 font-mono tracking-widest text-red-400 border-red-500/20 disabled:opacity-40"
          >
            {erasing ? 'ERASING…' : 'ERASE ALL'}
          </button>
        </div>
      </div>

      {logs == null ? (
        <div className="text-[10px] text-white/35">
          Connect to a flight controller and click <span className="font-mono text-white/60">LIST</span> to pull
          on-board logs via MAVLink (LOG_REQUEST_LIST / LOG_REQUEST_DATA).
        </div>
      ) : logs.length === 0 ? (
        <div className="text-[10px] text-white/35">No on-board logs reported.</div>
      ) : (
        <>
          <div className="text-[9px] font-mono text-white/30 mb-1.5">
            {logs.length} log{logs.length === 1 ? '' : 's'} · {(totalBytes / 1024 / 1024).toFixed(1)} MB
          </div>
          <div className="space-y-0.5 max-h-40 overflow-y-auto">
            {logs.map((log) => (
              <div
                key={log.id}
                className="flex items-center justify-between py-1 px-2 rounded border-b border-white/[0.03] last:border-0"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] font-mono text-white/70">
                    log_{log.id.toString().padStart(3, '0')}
                  </div>
                  <div className="text-[9px] text-white/35 font-mono">
                    {(log.size_bytes / 1024 / 1024).toFixed(2)} MB
                    {log.time_utc ? ` · ${new Date(log.time_utc * 1000).toISOString().replace('T', ' ').slice(0, 19)}` : ''}
                  </div>
                </div>
                <button
                  onClick={() => download(log)}
                  disabled={downloadingId !== null}
                  className="glass-button text-[9px] py-0.5 px-2 font-mono tracking-wider text-cyan-400 border-cyan-500/20 disabled:opacity-40"
                >
                  {downloadingId === log.id ? 'PULLING…' : 'DOWNLOAD'}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
      {error && (
        <div className="mt-2 p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-[10px] text-red-400 font-mono">
          {error}
        </div>
      )}
    </GlassPanel>
  );
}
