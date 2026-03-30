import { useState, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { clsx } from 'clsx';
import type { MissionConfig, InferencePath } from '../../data/missions';

interface MissionEditorProps {
  config: MissionConfig;
  onChange: (config: MissionConfig) => void;
}

function Tooltip({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);

  const show = useCallback(() => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    setPos({ x: rect.right + 10, y: rect.top + rect.height / 2 });
  }, []);

  const hide = useCallback(() => setPos(null), []);

  return (
    <span
      ref={ref}
      className="inline-flex items-center ml-1 cursor-help"
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      <span className="w-3.5 h-3.5 rounded-full bg-white/[0.06] border border-white/[0.10] flex items-center justify-center text-[8px] text-white/30 font-bold select-none">?</span>
      {pos && createPortal(
        <div
          className="fixed z-[9999] pointer-events-none animate-in fade-in duration-100"
          style={{ left: pos.x, top: pos.y, transform: 'translateY(-50%)' }}
        >
          <div className="px-3 py-2.5 rounded-lg bg-neutral-900 border border-white/15 text-[10px] text-white/85 leading-relaxed w-56 shadow-2xl shadow-black/60">
            {text}
          </div>
        </div>,
        document.body,
      )}
    </span>
  );
}

function NumberField({
  label,
  value,
  unit,
  step,
  min,
  max,
  tooltip,
  onChange,
}: {
  label: string;
  value: number;
  unit: string;
  step?: number;
  min?: number;
  max?: number;
  tooltip?: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-1.5">
      <label className="text-[10px] text-white/50 flex-shrink-0 flex items-center">
        {label}
        {tooltip && <Tooltip text={tooltip} />}
      </label>
      <div className="flex items-center gap-1.5">
        <input
          type="number"
          value={value}
          step={step ?? 0.1}
          min={min}
          max={max}
          aria-label={label}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          className="w-20 bg-white/[0.04] border border-white/[0.08] rounded-lg px-2 py-1
            text-[11px] font-mono text-white/80 text-right outline-none
            focus:border-white/20 focus:bg-white/[0.06] transition-all"
        />
        <span className="text-[9px] text-white/30 w-10 font-mono">{unit}</span>
      </div>
    </div>
  );
}

function SliderField({
  label,
  value,
  unit,
  step,
  min,
  max,
  tooltip,
  onChange,
}: {
  label: string;
  value: number;
  unit: string;
  step: number;
  min: number;
  max: number;
  tooltip?: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="py-1.5">
      <div className="flex items-center justify-between mb-1">
        <label className="text-[10px] text-white/50 flex items-center">
          {label}
          {tooltip && <Tooltip text={tooltip} />}
        </label>
        <span className="text-[10px] font-mono text-white/70">
          {value} {unit}
        </span>
      </div>
      <input
        type="range"
        value={value}
        step={step}
        min={min}
        max={max}
        aria-label={label}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1 rounded-full appearance-none bg-white/[0.08] cursor-pointer
          [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3
          [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white
          [&::-webkit-slider-thumb]:border-0 [&::-webkit-slider-thumb]:cursor-pointer"
      />
    </div>
  );
}

const INFER_OPTIONS: { value: InferencePath; label: string; desc: string }[] = [
  { value: 'onboard', label: 'Onboard AI', desc: 'Real-time detection in flight' },
  { value: 'rtn', label: 'Home Station', desc: 'VLM processing post-flight' },
  { value: 'both', label: 'Either', desc: 'Onboard or home station' },
];

export function MissionEditor({ config, onChange }: MissionEditorProps) {
  const update = <K extends keyof MissionConfig>(key: K, value: MissionConfig[K]) => {
    onChange({ ...config, [key]: value });
  };

  return (
    <div>
      <h2 className="text-[10px] font-semibold uppercase tracking-wider text-white/35 mb-3 px-1">
        <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-white/[0.06] border border-white/[0.10] text-[8px] text-white/40 mr-1.5 font-bold">2</span>
        Mission Parameters
      </h2>

      <div className="space-y-3">
        {/* Imaging */}
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="text-[9px] font-semibold uppercase tracking-widest text-white/50 mb-1.5">
            Imaging Requirements
          </div>
          <NumberField
            label="Min GSD"
            value={config.min_gsd_cm_per_px}
            unit="cm/px"
            step={0.1}
            min={0.1}
            max={20}
            tooltip="Ground Sample Distance — the real-world size of one pixel. Lower = sharper images. Determined by altitude, focal length, and sensor size."
            onChange={(v) => update('min_gsd_cm_per_px', v)}
          />
          <NumberField
            label="Min NIIRS"
            value={config.min_niirs}
            unit=""
            step={0.5}
            min={1}
            max={9}
            tooltip="National Imagery Interpretability Rating Scale. Higher = more detail visible. Level 6 can identify vehicles; level 8 can detect small hardware defects."
            onChange={(v) => update('min_niirs', v)}
          />
          <NumberField
            label="Target Feature"
            value={config.target_feature_mm}
            unit="mm"
            step={1}
            min={0.5}
            max={1000}
            tooltip="The smallest defect or feature you need to detect. The system calculates whether the camera can resolve features this small at the given altitude."
            onChange={(v) => update('target_feature_mm', v)}
          />
          <NumberField
            label="Exposure Time"
            value={config.exposure_time_s * 1000}
            unit="ms"
            step={0.1}
            min={0.01}
            max={100}
            tooltip="Camera shutter exposure time. Must match the actual sensor capability. Shorter exposure reduces motion blur but requires more light."
            onChange={(v) => update('exposure_time_s', v / 1000)}
          />
          <NumberField
            label="Max Blur"
            value={config.max_blur_px}
            unit="px"
            step={0.1}
            min={0.1}
            max={5}
            tooltip="Maximum acceptable motion blur in pixels. Sub-pixel (< 1.0) required for sharp imagery. 0.5 px recommended for detection tasks."
            onChange={(v) => update('max_blur_px', v)}
          />
        </div>

        {/* Flight */}
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="text-[9px] font-semibold uppercase tracking-widest text-white/50 mb-1.5">
            Flight Parameters
          </div>
          <SliderField
            label="Altitude AGL"
            value={config.nominal_altitude_m}
            unit="m"
            step={5}
            min={5}
            max={500}
            tooltip="Above Ground Level. Lower altitude gives better GSD but reduces coverage area per pass. Affects endurance and wind exposure."
            onChange={(v) => update('nominal_altitude_m', v)}
          />
          <SliderField
            label="Cruise Speed"
            value={config.nominal_speed_ms}
            unit="m/s"
            step={0.5}
            min={1}
            max={40}
            tooltip="Nominal flight speed during data collection. Faster covers more area but increases motion blur and reduces image overlap."
            onChange={(v) => update('nominal_speed_ms', v)}
          />
          <NumberField
            label="Min Endurance"
            value={config.min_endurance_min}
            unit="min"
            step={5}
            min={5}
            max={600}
            tooltip="Minimum flight time needed to complete the mission including transit, data collection, and return-to-home reserve."
            onChange={(v) => update('min_endurance_min', v)}
          />
        </div>

        {/* Payload & Environment */}
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="text-[9px] font-semibold uppercase tracking-widest text-white/50 mb-1.5">
            Payload & Environment
          </div>
          <NumberField
            label="Sensor Payload"
            value={config.required_payload_kg}
            unit="kg"
            step={0.5}
            min={0}
            max={30}
            tooltip="Total weight of cameras, sensors, and compute hardware. Must not exceed the aircraft's max payload capacity."
            onChange={(v) => update('required_payload_kg', v)}
          />
          <NumberField
            label="Max Wind"
            value={config.max_wind_ms}
            unit="m/s"
            step={1}
            min={0}
            max={30}
            tooltip="Maximum acceptable wind speed for safe and stable data collection. Exceeding this degrades image quality and risks flight safety."
            onChange={(v) => update('max_wind_ms', v)}
          />
        </div>

        {/* Inference */}
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="text-[9px] font-semibold uppercase tracking-widest text-white/50 mb-1.5">
            Inference Pipeline
          </div>
          <div className="space-y-1.5">
            {INFER_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => update('inference_path', opt.value)}
                className={clsx(
                  'w-full text-left flex items-center gap-2 px-2.5 py-2 rounded-lg border transition-all',
                  config.inference_path === opt.value
                    ? 'bg-white/[0.06] border-white/20'
                    : 'bg-white/[0.02] border-white/[0.05] hover:bg-white/[0.04]',
                )}
              >
                <div
                  className={clsx(
                    'w-2.5 h-2.5 rounded-full border-2 flex-shrink-0',
                    config.inference_path === opt.value
                      ? 'border-white bg-white'
                      : 'border-white/20',
                  )}
                />
                <div>
                  <div className="text-[10px] font-medium text-white/75">{opt.label}</div>
                  <div className="text-[9px] text-white/35">{opt.desc}</div>
                </div>
              </button>
            ))}
          </div>
          {config.inference_path !== 'onboard' && (
            <div className="mt-2">
              <NumberField
                label="Post-processing"
                value={config.post_processing_hrs}
                unit="hrs"
                step={0.5}
                min={0}
                max={24}
                tooltip="Estimated time for VLM/AI processing after the drone returns. Depends on data volume and model complexity."
                onChange={(v) => update('post_processing_hrs', v)}
              />
            </div>
          )}
        </div>

        {/* Energy & Fuel — not in datasheets */}
        <div className="rounded-xl border border-amber-500/10 bg-amber-500/[0.02] p-3">
          <div className="text-[9px] font-semibold uppercase tracking-widest text-amber-400/60 mb-0.5">
            Energy & Fuel
          </div>
          <div className="text-[8px] text-white/25 mb-1.5">Not in datasheets — verify for your aircraft</div>
          <NumberField
            label="Battery (VTOL)"
            value={config.battery_capacity_ah}
            unit="Ah"
            step={1}
            min={1}
            max={200}
            tooltip="Amp-hour capacity of the VTOL battery pack used for hover phases (takeoff, landing, transition). Not listed in VA-series datasheets."
            onChange={(v) => update('battery_capacity_ah', v)}
          />
          <NumberField
            label="Fuel Capacity"
            value={config.fuel_capacity_l}
            unit="L"
            step={0.5}
            min={0.5}
            max={50}
            tooltip="Usable fuel tank volume in liters. VA-series datasheets do not specify this — values here are estimates you should confirm."
            onChange={(v) => update('fuel_capacity_l', v)}
          />
          <NumberField
            label="Fuel Burn Rate"
            value={config.fuel_consumption_l_per_hr}
            unit="L/hr"
            step={0.1}
            min={0.1}
            max={20}
            tooltip="Fuel consumption at cruise power. VA-series datasheets do not specify this — values here are estimates you should confirm."
            onChange={(v) => update('fuel_consumption_l_per_hr', v)}
          />
        </div>

        {/* Optics & Analysis */}
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="text-[9px] font-semibold uppercase tracking-widest text-white/50 mb-1.5">
            Analysis Settings
          </div>
          <NumberField
            label="RER"
            value={config.rer}
            unit=""
            step={0.05}
            min={0.1}
            max={1.0}
            tooltip="Relative Edge Response — measures optical sharpness (0–1). 0.9 = well-focused system. Lower values degrade NIIRS. Change if your lens/sensor has known aberrations."
            onChange={(v) => update('rer', v)}
          />
          <SliderField
            label="Grid Resolution"
            value={config.grid_resolution}
            unit="pts"
            step={5}
            min={5}
            max={100}
            tooltip="Number of speed and altitude points per axis in the envelope analysis. Higher = finer detail but slower computation."
            onChange={(v) => update('grid_resolution', v)}
          />
          <div className="py-1.5">
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] text-white/50 flex items-center">
                UQ Method
                <Tooltip text="Uncertainty Quantification method. Deterministic = single-point evaluation (fast). Monte Carlo = probabilistic sampling for confidence intervals (slower but shows uncertainty)." />
              </label>
            </div>
            <div className="flex gap-1.5">
              {(['deterministic', 'monte_carlo'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => update('uq_method', m)}
                  className={clsx(
                    'flex-1 text-center px-2 py-1.5 rounded-lg border text-[9px] transition-all',
                    config.uq_method === m
                      ? 'bg-white/[0.06] border-white/20 text-white/80'
                      : 'bg-white/[0.02] border-white/[0.05] text-white/40 hover:bg-white/[0.04]',
                  )}
                >
                  {m === 'deterministic' ? 'Deterministic' : 'Monte Carlo'}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Thresholds */}
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="text-[9px] font-semibold uppercase tracking-widest text-white/50 mb-1.5">
            Decision Thresholds
          </div>
          <SliderField
            label="GO threshold"
            value={config.pass_threshold}
            unit=""
            step={0.05}
            min={0.5}
            max={1}
            tooltip="Minimum overall feasibility score to classify the mission as GO. Below this but above MARGINAL shows a warning."
            onChange={(v) => update('pass_threshold', v)}
          />
          <SliderField
            label="MARGINAL threshold"
            value={config.warn_threshold}
            unit=""
            step={0.05}
            min={0.3}
            max={config.pass_threshold}
            tooltip="Score below GO but above this threshold shows MARGINAL. Below this is a hard NO-GO. Adjust based on your risk tolerance."
            onChange={(v) => update('warn_threshold', v)}
          />
        </div>
      </div>
    </div>
  );
}
