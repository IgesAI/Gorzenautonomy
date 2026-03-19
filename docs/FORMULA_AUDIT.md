# Digital Twin Formula Audit

Complete audit of all formulas, variable correlations, and data flow in the VTOL digital twin platform.

---

## 1. Model Chain Overview

Models execute in strict order. Each model's outputs become `conditions` for the next. Data flows:

```
params (twin config) + conditions (runtime) → model.evaluate() → outputs → merged into conditions
```

**Execution order (17 models):**

| # | Model | Key Outputs | Feeds Into |
|---|-------|-------------|------------|
| 1 | Environment | air_density, ambient_light | Airframe, ICE, Battery, Comms, ImageQuality |
| 2 | Airframe | drag_N, rotor_lift_required_N, flight_mode_id | ICE (power), Rotor, Generator |
| 3 | ICE Engine | fuel_flow_rate_g_hr, engine_feasible | FuelSystem |
| 4 | Fuel System | fuel_endurance_hr, fuel_feasible | — |
| 5 | Rotor | rotor_power_total_W, rotor_torque_total_Nm | Motor, ESC |
| 6 | Motor | motor_power_elec_W | ESC |
| 7 | ESC | total_electrical_power_W | Battery, Generator |
| 8 | Battery | endurance_min, battery_feasible | — |
| 9 | Generator | generator_power_available_w | — |
| 10 | Avionics | geotag_error_m | — |
| 11 | Compute | effective_latency_ms, compute_power_W | ESC (via conditions), Identification |
| 12 | Comms | compression_quality_factor | Identification |
| 13 | GSD | gsd_cm_px, pixels_on_target | MotionBlur, RollingShutter, ImageQuality, Identification |
| 14 | Motion Blur | smear_pixels, safe_inspection_speed_ms | Identification |
| 15 | Rolling Shutter | rs_total_distortion_px | Identification |
| 16 | Image Quality | image_utility_score | Identification |
| 17 | Identification | identification_confidence | MCP constraint |

---

## 2. Envelope Solver Entry Point

**Cruise power estimation** (before model chain, in `evaluate_point`):

```
q = 0.5 × ρ × V²                    (dynamic pressure)
CL = W / (q × S)                    (lift coefficient for level flight)
Cdi = CL² / (π × AR × e)            (induced drag coefficient)
D = q × S × (cd0 + Cdi)             (total drag)
P_drag = D × V                      (power to overcome drag)
cruise_power_est = max(0.3, P_drag / 1000 / 0.6)   [kW]
```

**Why it matters:** Cruise power drives ICE fuel flow and engine feasibility. The 0.6 factor is propulsive efficiency; 0.3 kW minimum is ICE idle.

**Variables:** `wing_area_m2`, `cd0`, `oswald_efficiency`, `wing_span_m`, `mass_total_kg`, `airspeed_ms`

---

## 3. Environment Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `headwind = wind_speed × cos(wind_dir - heading)` | wind_speed_ms, wind_direction_deg | Wind component along flight path |
| `crosswind = wind_speed × sin(...)` | same | Lateral wind |
| `turbulence_intensity = wind_speed × 0.1 × gust_factor` | wind_speed_ms, gust_intensity | Turbulence severity |
| `ρ = 1.225 × (P/1013.25) × (288.15/T_actual)` | pressure_hpa, altitude_m, temperature_c | Air density (ideal gas, T_actual = ISA + temp offset) |

**Outputs:** `air_density_kgm3`, `ambient_light_lux_out`, `temperature_at_alt_c`

**Why they matter:** Density affects drag, rotor thrust, and ICE power. Light affects SNR in ImageQuality. Temperature affects ICE derating and battery resistance.

---

## 4. Airframe Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `wing_fraction = (v - v_trans_start) / (v_trans_end - v_trans_start)` | airspeed_ms, max_speed_ms | Transition blend (hover→cruise) |
| `wing_lift = q × S × CL × wing_fraction` | wing_area_m2, cl_alpha, alpha_rad | Wing-borne lift |
| `rotor_lift_required = W - wing_lift` | mass_total_kg | VTOL lift demand |
| `Cd_induced = CL² / (π × AR × e)` | oswald_efficiency, wing_span_m | Induced drag |
| `drag = q × S × (cd0 + Cd_induced)` | cd0 | Total drag |
| `power_parasitic = drag × v` | — | Parasitic power |
| `aero_feasible = (v ≤ Vne) ∧ (load_factor ≤ max_lf)` | max_speed_ms, max_load_factor | Structural limits |

**Outputs:** `rotor_lift_required_N`, `flight_mode_id`, `aero_feasible`

**Why they matter:** Rotor lift drives VTOL motor power and battery draw. Flight mode affects generator behavior (VTOL vs cruise).

---

## 5. ICE Engine Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `alt_factor = max(1 - 0.015×(density_alt_ft/1000), 0.3)` | density_altitude_ft, altitude_compensation | Altitude derating (EFI) |
| `temp_factor = max(1 - (temp-30)×0.005, 0.8)` if temp>30 | temperature_c | Hot-day derating |
| `available_kw = max_power_kw × alt_factor × temp_factor + hybrid_kw` | max_power_kw, hybrid_boost_power_kw | Available power |
| `throttle = power_demand / available_kw` | cruise_power_demand_kw | Throttle |
| `bsfc_actual = bsfc × (1 + 0.15×(1 - throttle))` | bsfc_cruise_g_kwh | Part-throttle BSFC degradation |
| `fuel_flow_g_hr = bsfc_actual × actual_power` | — | **Fuel consumption** |
| `engine_feasible = actual_power ≥ 0.95 × power_demand` | — | Power margin |

**Outputs:** `fuel_flow_rate_g_hr`, `engine_feasible`, `throttle_pct`

**Why they matter:** Fuel flow feeds FuelSystem for endurance. BSFC and throttle drive mission energy budget. UQ perturbs `bsfc_cruise_g_kwh` → affects fuel_endurance_hr and MCP.

---

## 6. Fuel System Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `fuel_burned_kg = fuel_flow_g_hr × elapsed_hr / 1000` | fuel_flow_rate_g_hr, mission_elapsed_hr | Fuel consumed |
| `fuel_remaining_kg = tank_kg - fuel_burned_kg` | tank_capacity_kg | Remaining fuel |
| `reserve_kg = tank_kg × fuel_reserve_pct` | fuel_reserve_pct | Reserve (not usable) |
| `usable_remaining = max(fuel_remaining - reserve_kg, 0)` | — | Usable fuel |
| **`fuel_endurance_hr = (usable_remaining × 1000) / fuel_flow_g_hr`** | — | **MCP constraint input** |
| `fuel_feasible = fuel_remaining > reserve_kg` | — | Reserve margin |

**Outputs:** `fuel_endurance_hr`, `fuel_feasible`

**Why they matter:** `fuel_endurance_hr` is a direct MCP constraint (≥ 1.0 hr). Driven by tank capacity, reserve policy, and ICE fuel flow.

---

## 7. Rotor Model (VTOL Lift)

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `thrust_per_rotor = rotor_lift_required_N / n_rotors` | rotor_count | Per-rotor thrust |
| `n_rps = √(thrust_per_rotor / (ct0 × ρ × D⁴))` | prop_ct_static, rotor_diameter_m | Rotor speed |
| `μ = v_fwd / v_tip` | airspeed_ms | Advance ratio |
| `ct_effective = ct0 × (1 - 0.3×μ²)` | — | Forward-flight thrust reduction |
| `cp_effective = cp0 × (1 + 0.5×μ²)` | prop_cp_static | Forward-flight power increase |
| `power_total = cp_effective × ρ × n_rps³ × D⁵ × n_rotors` | — | **Total VTOL power** |

**Outputs:** `rotor_power_total_W`, `rotor_torque_total_Nm`

**Why they matter:** Rotor power drives motor electrical demand and battery draw. Higher speed → more power (forward-flight penalty).

---

## 8. Motor Electrical Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `I = torque_per / kt` | motor_kt | Motor current |
| `V = back_emf + I×R` | motor_kv, motor_resistance_ohm | Terminal voltage |
| `P_elec = V × I × n_rotors` | — | Electrical power |

**Outputs:** `motor_power_elec_W`

**Why they matter:** Feeds ESC for total electrical load and battery current draw.

---

## 9. ESC Loss Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `conduction_loss = I² × R_esc` | esc_resistance_mohm | Ohmic losses |
| `switching_loss = P_motor × sw_pct` | esc_switching_loss_pct | Switching losses |
| `total_electrical_power_W = P_motor + esc_loss + compute_power + avionics_power` | — | **Total system load** |

**Outputs:** `total_electrical_power_W`

**Why they matter:** Total electrical load for battery endurance and generator demand. **Note:** Battery model uses `total_propulsion_power_W` (default 200) instead of `total_electrical_power_W` — potential mismatch.

---

## 10. Battery Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `OCV_cell = 3 + 1.2×soc - 0.6×soc² + 0.6×soc³` | soc | LiPo OCV curve |
| `I_total = power_draw / OCV_pack` | total_propulsion_power_W ⚠️ | Load current |
| `voltage_sag = I×(R0 + R1×0.63 + R_wiring)` | internal_resistance_mohm, soh_pct | Voltage sag |
| `terminal_v = OCV_pack - sag` | — | Under-load voltage |
| `endurance_min = usable_energy / (I_draw/60)` | — | **Battery reserve (min)** |
| `battery_feasible = terminal_v ≥ 3.3×n_s ∧ soc > 0.05` | — | Voltage and SoC limits |

**Outputs:** `endurance_min`, `battery_feasible`

**Why they matter:** `endurance_min` is reported as battery reserve. SoH affects capacity; temperature affects resistance. UQ perturbs `soh_pct`.

---

## 11. Generator Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `headroom = 1 - throttle_pct` | throttle_pct (from ICE) | Engine load headroom |
| `gen_available = gen_cont × headroom` | generator_output_w | Available electrical power |
| `charging = min(surplus, charge_rate)` if surplus>0 ∧ soc<95 | generator_charge_rate_w | Battery charging |

**Outputs:** `generator_power_available_w`, `generator_charging_w`

**Why they matter:** Hybrid VTOL: generator powers avionics/compute and can charge battery during cruise.

---

## 12. Avionics Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `pos_unc = √(gps_noise² + ekf_pos²)` | gps_type, ekf_position_noise_m | Position uncertainty |
| `geotag_error = √(pos² + (v×timing_err)² + (alt×heading_err)²)` | airspeed_ms, altitude_m | Geotag accuracy |

**Outputs:** `geotag_error_m`, `position_uncertainty_m`

**Why they matter:** Geotag error affects mapping quality; not directly in MCP but relevant for mission quality.

---

## 13. Compute Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `junction_temp = ambient + max_power × R_th` | max_power_w, temperature_at_alt_c | Thermal model |
| `throttle_factor = max(0.3, 1 - (T_j - T_throttle)/30)` if T_j > T_throttle | thermal_throttle_temp_c | Thermal throttling |
| `effective_latency_ms = base_latency / throttle_factor` | inference_latency_ms | Degraded latency |
| `compute_power_W = max_power × throttle_factor` | — | Actual power draw |

**Outputs:** `effective_latency_ms`, `compute_power_W`

**Why they matter:** `effective_latency_ms` feeds Identification (latency penalty). Compute power feeds ESC total load.

---

## 14. Comms Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `FSPL = 20×log10(d) + 20×log10(f) + 32.44` | distance_to_gcs_km | Free-space path loss |
| `link_margin = tx_power + 2×ant_gain - FSPL - rx_sens` | tx_power_dbm, antenna_gain_dbi | Link budget |
| `available_bw = manet_bw` if in range else `satcom_bw` | manet_bandwidth_mbps, satcom_available | Bandwidth |
| **`quality_factor = 90 × (available_bw / encoding_bitrate)`** if encoding > bw | encoding_bitrate_mbps | **Bandwidth-limited compression** |
| `quality_factor = 90` if encoding ≤ bw | — | Full quality |

**Outputs:** `compression_quality_factor`, `link_margin_db`

**Why they matter:** `compression_quality_factor` directly drives Identification confidence. If `encoding_bitrate > manet_bandwidth`, quality drops → compression penalty → lower identification_confidence → MCP failure.

---

## 15. GSD Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| **`GSD_w = (sensor_width_mm × altitude_m) / (focal_length_mm × pixel_width)`** | sensor_width_mm, focal_length_mm, pixel_width | Ground sample distance (width) |
| `GSD_h = (sensor_height_mm × alt) / (focal_length × pixel_height)` | sensor_height_mm, pixel_height | GSD (height) |
| `gsd_cm_px = max(GSD_w, GSD_h) × 100` | — | Worst-case GSD (cm/px) |
| **`pixels_on_target = target_size_m / (gsd_cm_px/100)`** | target_size_m | **Pixels covering target** |

**Outputs:** `gsd_cm_px`, `pixels_on_target`

**Why they matter:** GSD drives motion blur (smear_pixels), rolling shutter distortion, and pixel density factor in Identification. Lower altitude → better GSD → more pixels on target → higher confidence.

---

## 16. Motion Blur Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| **`smear_distance = v_ground × t_exposure`** | airspeed_ms, exposure_time_s | Ground travel during exposure |
| **`smear_pixels = smear_distance / GSD`** | gsd_cm_px | Blur in pixels |
| `total_blur = √(smear_px² + vibration_blur²)` | vibration_blur_px | Combined blur |
| `motion_blur_feasible = total_blur ≤ max_blur_px` | max_blur_px | Feasibility |
| `safe_inspection_speed = blur_budget × GSD / t_exposure` | — | Max speed for acceptable blur |

**Outputs:** `smear_pixels`, `safe_inspection_speed_ms`, `motion_blur_feasible`

**Why they matter:** Higher speed → more smear → blur penalty in Identification → lower confidence. `exposure_time_s` is fixed at 1/2000 s in envelope solver.

---

## 17. Rolling Shutter Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `ground_travel = v_ground × t_readout` | airspeed_ms, readout_time_ms | Travel during readout |
| `skew_px = ground_travel / GSD` | gsd_cm_px | Translational skew |
| `wobble_px = angular_rate_rps × t_readout × pixel_height` | angular_rate_dps, pixel_height | Angular distortion |
| **`rs_total_distortion_px = √(skew² + wobble²)`** | — | **Total RS distortion** |

**Outputs:** `rs_total_distortion_px`

**Why they matter:** RS distortion contributes to blur penalty in Identification (weighted 1%, cap 0.5). Global shutter → zero. High speed + long readout → large distortion.

---

## 18. Image Quality Model (GIQE-inspired)

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `blur_mtf = sinc(blur_px × 0.5)` | smear_pixels | Blur degrades MTF |
| `system_mtf = lens_mtf × sampling_mtf × blur_mtf` | lens_mtf_nyquist | Combined MTF |
| `compression_mtf = 0.7 + 0.3 × min(jpeg_q, comp_qf)/100` | compression_quality_factor | Compression effect |
| `NIIRS = c0 + c1×log10(GSD) + c2×log10(RER) + c3/SNR` | gsd_cm_px, ambient_light | GIQE-like score |
| **`image_utility_score = NIIRS / 9`** | — | **0–1 utility** |

**Outputs:** `image_utility_score`

**Why they matter:** Multiplicative factor in Identification confidence. Low light, high GSD, or high compression → lower utility.

---

## 19. Identification Confidence Model

| Formula | Variables | Purpose |
|---------|-----------|---------|
| `rs_contribution = min(rs_distortion × 0.01, 0.5)` | rs_total_distortion_px | RS penalty (correctable) |
| `total_blur = √(smear_px² + rs_contribution²)` | smear_pixels | Effective blur |
| `blur_penalty = min(total_blur × deg_per_blur, 0.5)` | accuracy_degradation_per_blur_px | Blur degradation |
| `q_deficit = max(0, 90 - effective_q) / 10` | jpeg_quality, compression_quality_factor | Compression deficit |
| `compression_penalty = min(q_deficit × deg_per_q10, 0.3)` | accuracy_degradation_per_jpeg_q10 | Compression degradation |
| `pixel_density_factor = 1` if pot ≥ 0.1×input_res else `pot/(0.1×input_res)` | pixels_on_target, input_resolution_px | Resolution adequacy |
| `latency_penalty = min(latency_ms/1000×0.1, 0.1)` | effective_latency_ms | Staleness penalty |
| **`confidence = acc_nominal × pixel_density × (1-blur) × (1-compression) × (1-latency) × image_utility`** | accuracy_at_nominal | **Final P(identification)** |

**Outputs:** `identification_confidence`

**Why they matter:** **Primary MCP constraint** (≥ min_identification_confidence, default 0.8). All perception factors multiply: blur, compression, pixel density, latency, image utility. Any one can tank confidence.

---

## 20. Mission Completion Probability (MCP)

```
MCP = P(all constraints satisfied)
    = mean over Monte Carlo samples of: (fuel_endurance_hr ≥ 1.0) ∧ (identification_confidence ≥ min_ident)
```

**UQ inputs (perturbed):** wind_speed_ms, bsfc_cruise_g_kwh, mass_total_kg, cd0, soh_pct, temperature_c

**Constraint chain:**
- `fuel_endurance_hr` ← FuelSystem ← fuel_flow ← ICE ← cruise_power ← drag ← mass, cd0, speed, altitude
- `identification_confidence` ← Identification ← blur, compression, pixels, latency, image_utility ← GSD, MotionBlur, RS, Comms, Compute, ImageQuality

**Why UQ inputs matter:**
- **bsfc_cruise_g_kwh**: Higher BSFC → more fuel flow → lower endurance
- **mass_total_kg**: Heavier → more drag → more power → more fuel flow → lower endurance
- **cd0**: Higher drag → more power → more fuel flow
- **soh_pct**: Lower SoH → less battery capacity (affects endurance_min, not fuel_endurance)
- **temperature_c**: Affects ICE derating and battery resistance
- **wind_speed_ms**: Not directly in fuel or ident formulas in current chain; available for future coupling

---

## 21. Feasibility Surface (Grid)

For each (speed, altitude) point:

```
feasible = aero_feasible ∧ engine_feasible ∧ fuel_feasible ∧ motion_blur_feasible ∧ battery_feasible ∧ (alt ≤ service_ceiling)
```

---

## 22. Variable Correlation Summary

| Output | Key Drivers | Why |
|--------|-------------|-----|
| fuel_endurance_hr | tank_capacity, fuel_reserve_pct, bsfc, cruise_power, mass, cd0 | More fuel, less burn, lower drag → longer endurance |
| identification_confidence | encoding_bitrate, manet_bandwidth, GSD, speed, exposure, readout, accuracy_at_nominal | Bandwidth vs bitrate, blur vs GSD/speed, RS vs speed/readout |
| mission_completion_probability | fuel_endurance_hr, identification_confidence | Both constraints must pass |
| safe_inspection_speed_ms | GSD, max_blur_px, exposure_time_s | Lower GSD, stricter blur → lower safe speed |
| endurance_min (battery) | total_electrical_power_W, soc, capacity, soh | Higher load, lower SoC/cap → less reserve |

---

## 23. Cross-References & Verification (Design Doc + Research)

| Formula | Source | Status |
|---------|--------|--------|
| GSD = (sensor_width × altitude) / (focal_length × image_width) | Design doc, DJI guidance | ✓ Implemented; use max(w,h) for worst-case |
| smear_distance = v_ground × t_exposure | Design doc p.4 | ✓ |
| smear_pixels = smear_distance / GSD | Design doc p.4 | ✓ |
| CDi = CL² / (π × AR × e) | NASA Glenn, standard aero | ✓ |
| BSFC: fuel_flow = BSFC × power | Wikipedia, x-engineer.org | ✓ |
| T = CT × ρ × n² × D⁴ | Actuator disk theory | ✓ |
| FSPL = 20 log₁₀(d) + 20 log₁₀(f) + 32.45 | ITU-R, Wikipedia | ✓ (was 32.44) |
| RS skew = (v × t_readout) / GSD | Pix4D, research | ✓ |
| RS wobble = angular_rate × t × focal_length_px | Phase One, angular blur | ✓ (fixed: was px_h) |
| ρ = ρ₀(P/P₀)(T₀/T) | Ideal gas, ISA | ✓ (fixed: was missing temp offset) |

---

## 24. Corrections Applied (Formula Audit)

1. **Environment density**: Added temperature offset — `T_actual = T_ISA + (temp - 15)` per ideal gas law.
2. **FSPL constant**: 32.44 → 32.45 (ITU-R standard).
3. **Battery model**: Now uses `total_electrical_power_W` from ESC (was `total_propulsion_power_W`).
4. **Rolling shutter wobble**: Uses `focal_length_px = (focal_length_mm / sensor_height_mm) × pixel_height` per Phase One/Pix4D angular blur formula.

---

## 25. Remaining Gaps

1. **ESC model** uses default 15 W compute, 10 W avionics (Compute/Avionics run after ESC).
2. **Exposure time** hardcoded 1/2000 s in envelope solver; not from payload schema.

---

## 26. Online Resource Verification (Full Audit)

All formulas and constants were cross-checked against authoritative online sources.

| Domain | Formula/Constant | Source | Status |
|--------|-----------------|--------|--------|
| **ISA** | T[K] = 288.15 − 0.0065×h[m] | Wikipedia, Engineering LibreTexts | ✓ |
| **ISA** | Lapse rate 6.5°C/km | Standard atmosphere | ✓ |
| **FSPL** | 20×log₁₀(d) + 20×log₁₀(f) + 32.45 (d km, f MHz) | ITU-R P.525 | ✓ |
| **Induced drag** | CDi = CL²/(π×AR×e) | NASA Glenn, Wikipedia | ✓ |
| **Rotor thrust** | T = CT×ρ×n²×D⁴ | NASA, propeller handbooks | ✓ |
| **Rotor power** | P = CP×ρ×n³×D⁵ | Actuator disk theory | ✓ |
| **GSD** | GSD = (sensor_width×altitude)/(focal_length×pixel_width) | DJI, Omnicalculator, Wikipedia | ✓ |
| **Motion blur** | smear_px = (v×t_exposure)/GSD | Design doc, standard | ✓ |
| **RS wobble** | wobble_px = angular_rate×t×focal_length_px | Phase One, Pix4D | ✓ |
| **LiPo OCV** | 3.0V @ 0%, 4.2V @ 100% | Industry datasheets | ✓ (polynomial approx) |
| **GIQE 4.0** | c0=10.251, c1=-3.32, c2=1.559, c3=-0.334, c4=-0.656 | NGA/OPTICS GIQE 4.0 | ✓ (corrected) |

---

## 27. Corrections Applied (Full Audit 2025)

1. **Environment density**: Added temperature offset — `T_actual = T_ISA + (temp - 15)` per ideal gas law.
2. **FSPL constant**: 32.44 → 32.45 (ITU-R P.525 standard).
3. **Battery model**: Uses `total_electrical_power_W` from ESC (was `total_propulsion_power_W`).
4. **Rolling shutter wobble**: Uses `focal_length_px = (focal_length_mm/sensor_height_mm)×pixel_height` per Phase One/Pix4D.
5. **RotorModel**: Now uses `air_density_kgm3` from Environment when available (pressure/temp-corrected); falls back to ISA.
6. **AirframeModel**: Same — uses Environment `air_density_kgm3` when available.
7. **GIQE coefficients**: Aligned with GIQE 4.0 (RER≥0.9): c2=1.559, c3=-0.334, c4=-0.656.
8. **Envelope solver**: Replaced hardcoded 3.14159 with `np.pi`.
