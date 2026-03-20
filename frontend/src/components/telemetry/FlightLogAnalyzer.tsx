import React, { useState, useRef } from 'react';
import { GlassPanel } from '../layout/GlassPanel';
import { chartStyles } from '../../theme/chartStyles';
import { colors } from '../../theme/tokens';
import { api } from '../../api/client';

interface LogSummary {
  filename: string;
  duration_s: number;
  topics: string[];
  parameter_count: number;
  message_count: number;
  vehicle_uuid: string;
  software_version: string;
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
  const [summary, setSummary] = useState<LogSummary | null>(null);
  const [calibration, setCalibration] = useState<CalibrationData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTopics, setSelectedTopics] = useState<Set<string>>(new Set(['battery_status', 'vehicle_local_position', 'airspeed_validated']));
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (file: File) => {
    setLoading(true);
    setError(null);
    setSummary(null);
    setCalibration(null);
    try {
      // Upload for summary and calibration data in parallel
      const [sumRes, calRes] = await Promise.all([
        api.telemetry.uploadLog(file),
        api.telemetry.uploadCalibration(file),
      ]);
      setSummary(sumRes.summary);
      setCalibration(calRes);
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

  return (
    <div className="h-full overflow-y-auto space-y-3 p-3">
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
            ref={fileRef} type="file" accept=".ulg" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(f); }}
          />
          {loading ? (
            <div className="text-white/50 text-sm">Parsing flight log...</div>
          ) : (
            <>
              <div className="text-white/50 text-sm mb-1">Drop .ulg file here or click to browse</div>
              <div className="text-white/30 text-[10px]">PX4 uLog flight recording</div>
            </>
          )}
        </div>
        {error && <div className="mt-2 text-xs text-red-400">{error}</div>}
      </GlassPanel>

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
            </div>
          </GlassPanel>

          {/* Battery Stats */}
          {calibration?.stats && (
            <GlassPanel padding="p-4">
              <h3 className={chartStyles.title}>Battery Analysis</h3>
              <div className="grid grid-cols-4 gap-3 mt-3">
                <div>
                  <div className={chartStyles.label}>Start V</div>
                  <div className="text-sm font-bold font-mono text-emerald-400">{calibration.stats.battery_start_v.toFixed(1)}</div>
                </div>
                <div>
                  <div className={chartStyles.label}>End V</div>
                  <div className="text-sm font-bold font-mono text-amber-400">{calibration.stats.battery_end_v.toFixed(1)}</div>
                </div>
                <div>
                  <div className={chartStyles.label}>Min V</div>
                  <div className="text-sm font-bold font-mono text-red-400">{calibration.stats.battery_min_v.toFixed(1)}</div>
                </div>
                <div>
                  <div className={chartStyles.label}>Duration</div>
                  <div className="text-sm font-bold font-mono text-white/90">{formatDuration(calibration.stats.flight_duration_s)}</div>
                </div>
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
