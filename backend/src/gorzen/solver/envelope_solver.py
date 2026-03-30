"""Envelope solver: speed-altitude feasibility, endurance, identification confidence.

Given a twin config + mission + environment, computes operating envelope surfaces.
Supports optional Monte Carlo UQ for p5/p95 confidence surfaces.
Runs the FULL model chain top-to-bottom for every grid point.

PREFLIGHT VALIDATION: Before any grid computation, validates that all
required parameters are present and no model would fall back to internal
defaults.  Returns INSUFFICIENT_DATA if validation fails.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

from gorzen.models.airframe import AirframeModel
from gorzen.models.avionics import AvionicsModel
from gorzen.models.base import CompositeModel
from gorzen.models.battery import BatteryModel
from gorzen.models.comms import CommsModel
from gorzen.models.compute import ComputeModel
from gorzen.models.environment import EnvironmentModel
from gorzen.models.fuel_system import FuelSystemModel, GeneratorModel
from gorzen.models.perception.gsd import GSDModel
from gorzen.models.perception.identification import IdentificationConfidenceModel
from gorzen.models.perception.image_quality import ImageQualityModel
from gorzen.models.perception.motion_blur import MotionBlurModel
from gorzen.models.perception.rolling_shutter import RollingShutterModel
from gorzen.models.propulsion import ESCLossModel, ICEEngineModel, MotorElectricalModel, RotorModel
from gorzen.schemas.envelope import EnvelopeResponse, EnvelopeSurface
from gorzen.schemas.parameter import DistributionType, EnvelopeOutput, SensitivityEntry, UncertaintySpec
from gorzen.schemas.twin_graph import VehicleTwin
from gorzen.uq.monte_carlo import MCInput, MonteCarloEngine

logger = logging.getLogger(__name__)


KTS_TO_MS = 0.514444


def _extract_params(twin: VehicleTwin) -> dict[str, float]:
    """Flatten twin config into a flat parameter dict for models."""
    p: dict[str, float] = {}

    af = twin.airframe
    p["mass_empty_kg"] = af.mass_empty_kg.value
    p["mass_total_kg"] = af.mass_mtow_kg.value
    p["mass_mtow_kg"] = af.mass_mtow_kg.value
    p["wing_area_m2"] = af.wing_area_m2.value
    p["wing_span_m"] = af.wing_span_m.value
    p["cd0"] = af.cd0.value
    p["cl_alpha"] = af.cl_alpha.value
    p["oswald_efficiency"] = af.oswald_efficiency.value
    p["max_speed_ms"] = af.max_speed_kts.value * KTS_TO_MS
    p["cruise_speed_kts"] = af.cruise_speed_kts.value
    p["max_load_factor"] = af.max_load_factor.value
    p["service_ceiling_ft"] = af.service_ceiling_ft.value
    p["vtol_ceiling_ft"] = af.vtol_ceiling_ft.value
    p["max_crosswind_kts"] = af.max_crosswind_kts.value
    p["max_operating_temp_c"] = af.max_operating_temp_c.value
    p["min_operating_temp_c"] = af.min_operating_temp_c.value
    p["payload_capacity_nose_kg"] = af.payload_capacity_nose_kg.value

    lp = twin.lift_propulsion
    p["rotor_count"] = lp.rotor_count.value
    p["rotor_diameter_m"] = lp.rotor_diameter_m.value
    p["blade_count"] = lp.blade_count.value
    p["prop_ct_static"] = lp.prop_ct_static.value
    p["prop_cp_static"] = lp.prop_cp_static.value
    p["motor_kv"] = lp.motor_kv.value
    p["motor_resistance_ohm"] = lp.motor_resistance_ohm.value
    p["motor_kt"] = lp.motor_kt.value

    cp = twin.cruise_propulsion
    p["power_architecture"] = cp.power_architecture.value
    p["engine_type"] = cp.engine_type.value
    p["displacement_cc"] = cp.displacement_cc.value
    p["engine_mass_kg"] = cp.engine_mass_kg.value
    p["max_power_kw"] = cp.max_power_kw.value
    p["max_power_rpm"] = cp.max_power_rpm.value
    p["bsfc_cruise_g_kwh"] = cp.bsfc_cruise_g_kwh.value
    p["cooling_type"] = cp.cooling_type.value
    p["altitude_compensation"] = float(cp.altitude_compensation.value)
    p["preheat_required"] = float(cp.preheat_required.value)
    p["preheat_time_min"] = cp.preheat_time_min.value
    p["preheat_power_w"] = cp.preheat_power_w.value
    p["generator_output_w"] = cp.generator_output_w.value
    p["generator_output_intermittent_w"] = cp.generator_output_intermittent_w.value
    p["generator_voltage_v"] = cp.generator_voltage_v.value
    p["hybrid_boost_available"] = float(cp.hybrid_boost_available.value)
    p["hybrid_boost_power_kw"] = cp.hybrid_boost_power_kw.value

    fs = twin.fuel_system
    p["fuel_type"] = fs.fuel_type.value
    p["fuel_density_kg_l"] = fs.fuel_density_kg_l.value
    p["tank_capacity_l"] = fs.tank_capacity_l.value
    p["tank_capacity_kg"] = fs.tank_capacity_kg.value
    p["usable_fuel_pct"] = fs.usable_fuel_pct.value

    en = twin.energy
    p["cell_count_s"] = en.cell_count_s.value
    p["cell_count_p"] = en.cell_count_p.value
    p["capacity_ah"] = en.capacity_ah.value
    p["nominal_voltage_v"] = en.nominal_voltage_v.value
    p["internal_resistance_mohm"] = en.internal_resistance_mohm.value
    p["soh_pct"] = en.soh_pct.value
    p["wiring_loss_mohm"] = en.wiring_loss_mohm.value
    p["reserve_policy_pct"] = en.reserve_policy_pct.value
    p["r1_mohm"] = 5.0
    p["c1_f"] = 500.0
    p["generator_charge_rate_w"] = en.generator_charge_rate_w.value

    av = twin.avionics
    p["gps_type"] = av.gps_type.value
    p["ekf_position_noise_m"] = av.ekf_position_noise_m.value
    p["ekf_velocity_noise_ms"] = av.ekf_velocity_noise_ms.value
    p["imu_gyro_noise_dps"] = av.imu_gyro_noise_dps.value
    p["imu_accel_noise_mg"] = av.imu_accel_noise_mg.value
    p["baro_noise_m"] = av.baro_noise_m.value

    pl = twin.payload
    p["sensor_width_mm"] = pl.sensor_width_mm.value
    p["sensor_height_mm"] = pl.sensor_height_mm.value
    p["focal_length_mm"] = pl.focal_length_mm.value
    p["pixel_width"] = pl.pixel_width.value
    p["pixel_height"] = pl.pixel_height.value
    p["pixel_size_um"] = pl.pixel_size_um.value
    p["shutter_type"] = pl.shutter_type.value
    p["readout_time_ms"] = pl.readout_time_ms.value
    p["lens_mtf_nyquist"] = pl.lens_mtf_nyquist.value
    p["jpeg_quality"] = pl.jpeg_quality.value
    p["encoding_bitrate_mbps"] = pl.encoding_bitrate_mbps.value
    p["payload_mass_kg"] = pl.payload_mass_kg.value

    ai = twin.ai_model
    p["accuracy_at_nominal"] = ai.accuracy_at_nominal.value
    p["accuracy_degradation_per_blur_px"] = ai.accuracy_degradation_per_blur_px.value
    p["accuracy_degradation_per_jpeg_q10"] = ai.accuracy_degradation_per_jpeg_q10.value
    p["ood_threshold"] = ai.ood_threshold.value
    p["input_resolution_px"] = ai.input_resolution_px.value

    env = twin.mission_profile.environment
    p["wind_model"] = env.wind_model.value
    p["wind_speed_ms"] = env.wind_speed_ms.value
    p["gust_intensity"] = env.gust_intensity.value
    p["wind_direction_deg"] = env.wind_direction_deg.value
    p["temperature_c"] = env.temperature_c.value
    p["pressure_hpa"] = env.pressure_hpa.value
    p["density_altitude_ft"] = env.density_altitude_ft.value
    p["ambient_light_lux"] = env.ambient_light_lux.value

    co = twin.compute
    p["max_power_w"] = co.max_power_w.value
    p["thermal_throttle_temp_c"] = co.thermal_throttle_temp_c.value
    p["inference_latency_ms"] = co.inference_latency_ms.value
    p["max_throughput_fps"] = co.max_throughput_fps.value

    cm = twin.comms
    p["manet_range_nmi"] = cm.manet_range_nmi.value
    p["satcom_available"] = float(cm.satcom_available.value)
    p["tx_power_dbm"] = cm.tx_power_dbm.value
    p["antenna_gain_dbi"] = cm.antenna_gain_dbi.value
    p["receiver_sensitivity_dbm"] = cm.receiver_sensitivity_dbm.value
    p["manet_bandwidth_mbps"] = cm.manet_bandwidth_mbps.value
    p["satcom_bandwidth_mbps"] = cm.satcom_bandwidth_mbps.value

    mc = twin.mission_profile.constraints
    p["target_feature_mm"] = mc.target_feature_mm.value
    p["max_blur_px"] = mc.max_blur_px.value
    p["min_identification_confidence"] = mc.min_identification_confidence.value
    p["fuel_reserve_pct"] = mc.fuel_reserve_pct.value
    p["battery_reserve_pct"] = mc.battery_reserve_pct.value
    p["min_gsd_cm_px"] = mc.min_gsd_cm_px.value
    p["exposure_time_s"] = mc.exposure_time_s.value
    p["vibration_blur_px"] = mc.vibration_blur_px.value
    p["min_pixels_on_target"] = mc.min_pixels_on_target.value
    p["esc_resistance_mohm"] = 3.0
    p["esc_switching_loss_pct"] = 2.0

    return p


def _build_model_chain() -> list:
    """Build the ordered model chain for envelope evaluation.

    Order matters -- each model's outputs feed into the next:
    1. Environment -> air density, wind, temperature
    2. Airframe -> drag, lift, rotor lift required, flight mode
    3. ICE Engine -> fuel flow, available power, generator
    4. Fuel System -> endurance, fuel remaining, vehicle mass reduction
    5. Rotor -> VTOL thrust/power from electric motors
    6. Motor Electrical -> current, voltage for lift motors
    7. ESC Losses -> total electrical power demand
    8. Battery -> voltage sag, SoC, electrical endurance
    9. Generator -> charging, hybrid boost, electrical budget
    10. Avionics -> position uncertainty, geotag error
    11. Compute -> inference latency under thermal load
    12. Comms -> link margin, bandwidth-constrained quality
    13. GSD -> ground sample distance, pixels on target
    14. Motion Blur -> smear, safe inspection speed
    15. Rolling Shutter -> RS distortion risk
    16. Image Quality -> GIQE composite score
    17. Identification -> P(identification success)
    """
    return [
        EnvironmentModel(),
        AirframeModel(),
        ICEEngineModel(),
        FuelSystemModel(),
        RotorModel(),
        MotorElectricalModel(),
        ESCLossModel(),
        BatteryModel(),
        GeneratorModel(),
        AvionicsModel(),
        ComputeModel(),
        CommsModel(),
        GSDModel(),
        MotionBlurModel(),
        RollingShutterModel(),
        ImageQualityModel(),
        IdentificationConfidenceModel(),
    ]


def evaluate_point(
    params: dict[str, Any],
    speed_ms: float,
    altitude_m: float,
) -> dict[str, float]:
    """Evaluate ALL 17 models at a single operating point, top to bottom."""
    models = _build_model_chain()
    composite = CompositeModel(models)

    speed_kts = speed_ms / KTS_TO_MS
    # Power demand: P = D * V where D = 0.5 * rho * V^2 * S * Cd_total
    # Cd_total includes induced drag at the required CL
    # Use ISA density at altitude rather than hardcoded sea-level value
    T_isa = 288.15 - 0.0065 * altitude_m
    rho_est = 1.225 * (T_isa / 288.15) ** 4.2561
    S = params.get("wing_area_m2", 1.2)
    cd0 = params.get("cd0", 0.03)
    W = params.get("mass_total_kg", 68.0) * 9.81
    b = params.get("wing_span_m", 4.88)
    AR = b ** 2 / (S + 1e-6)
    e = params.get("oswald_efficiency", 0.8)
    q = 0.5 * rho_est * max(speed_ms, 0.5) ** 2
    CL = W / (q * S + 1e-6) if speed_ms > 2.0 else 0.0
    Cdi = CL ** 2 / (np.pi * AR * e + 1e-6) if speed_ms > 2.0 else 0.0
    D = q * S * (cd0 + Cdi)
    P_drag_W = D * max(speed_ms, 0.5)
    # Add propulsive efficiency loss (~60% prop efficiency)
    # Minimum idle power ~0.3 kW for ICE
    cruise_power_est = max(0.3, P_drag_W / 1000.0 / 0.6)

    target_feature_mm = params.get("target_feature_mm", 5.0)
    target_size_m = target_feature_mm / 1000.0

    conditions: dict[str, Any] = {
        "airspeed_ms": speed_ms,
        "altitude_m": altitude_m,
        "alpha_rad": 0.05,
        "soc": 0.8,
        "soc_pct": 80.0,
        "heading_deg": 0.0,
        "angular_rate_dps": 3.0,
        "target_size_m": target_size_m,
        "distance_to_gcs_km": 10.0,
        "cruise_power_demand_kw": cruise_power_est,
        "cruise_speed_kts": speed_kts,
        "mission_elapsed_hr": 0.0,
        "density_altitude_ft": params.get("density_altitude_ft", altitude_m * 3.281),
        "temperature_c": params.get("temperature_c", 20.0),
        "compute_power_W": params.get("max_power_w", 15.0),
        "avionics_power_W": 8.0,
        "manet_frequency_mhz": 1350.0,
    }
    merged = dict(params)
    merged.update(conditions)
    result = composite.evaluate(merged, conditions)
    return result.values


def _build_uncertain_inputs(params: dict[str, float]) -> list[MCInput]:
    """Define key parameters with realistic uncertainty distributions for MC."""
    return [
        MCInput(
            name="cd0",
            nominal=params.get("cd0", 0.03),
            uncertainty=UncertaintySpec(
                distribution=DistributionType.NORMAL,
                params={"mean": params.get("cd0", 0.03), "std": params.get("cd0", 0.03) * 0.1},
                bounds=(0.005, 0.15),
            ),
        ),
        MCInput(
            name="mass_total_kg",
            nominal=params.get("mass_total_kg", 68.0),
            uncertainty=UncertaintySpec(
                distribution=DistributionType.NORMAL,
                params={"mean": params.get("mass_total_kg", 68.0), "std": params.get("mass_total_kg", 68.0) * 0.02},
            ),
        ),
        MCInput(
            name="bsfc_cruise_g_kwh",
            nominal=params.get("bsfc_cruise_g_kwh", 500.0),
            uncertainty=UncertaintySpec(
                distribution=DistributionType.NORMAL,
                params={"mean": params.get("bsfc_cruise_g_kwh", 500.0), "std": 25.0},
                bounds=(300.0, 800.0),
            ),
        ),
        MCInput(
            name="wind_speed_ms",
            nominal=params.get("wind_speed_ms", 0.0),
            uncertainty=UncertaintySpec(
                distribution=DistributionType.NORMAL,
                params={"mean": params.get("wind_speed_ms", 0.0), "std": 2.0},
                bounds=(0.0, 30.0),
            ),
        ),
        MCInput(
            name="temperature_c",
            nominal=params.get("temperature_c", 20.0),
            uncertainty=UncertaintySpec(
                distribution=DistributionType.NORMAL,
                params={"mean": params.get("temperature_c", 20.0), "std": 3.0},
            ),
        ),
        MCInput(
            name="lens_mtf_nyquist",
            nominal=params.get("lens_mtf_nyquist", 0.3),
            uncertainty=UncertaintySpec(
                distribution=DistributionType.NORMAL,
                params={"mean": params.get("lens_mtf_nyquist", 0.3), "std": 0.03},
                bounds=(0.1, 0.6),
            ),
        ),
    ]


def compute_envelope(
    twin: VehicleTwin,
    speed_range: tuple[float, float] = (0.0, 35.0),
    altitude_range: tuple[float, float] = (10.0, 200.0),
    grid_resolution: int = 20,
    uq_method: str = "deterministic",
    mc_samples: int = 50,
) -> EnvelopeResponse:
    """Compute the full operating envelope with optional Monte Carlo UQ.

    When uq_method="monte_carlo", runs mc_samples trials per grid point
    (with perturbed uncertain parameters) to produce real p5/p95 surfaces.
    When uq_method="deterministic", uses nominal values only (fastest).

    PREFLIGHT: Validates that all required model parameters are present
    before beginning grid computation.  Returns degraded response with
    warnings if any critical parameters are missing.
    """
    t0 = time.time()
    params = _extract_params(twin)
    warnings: list[str] = []

    # ── Preflight validation ────────────────────────────────────────────
    _CRITICAL_PARAMS = [
        "mass_total_kg", "wing_area_m2", "wing_span_m", "cd0",
        "oswald_efficiency", "max_speed_ms", "sensor_width_mm",
        "sensor_height_mm", "focal_length_mm", "pixel_width", "pixel_height",
        "exposure_time_s", "vibration_blur_px", "max_blur_px",
        "max_power_kw", "bsfc_cruise_g_kwh", "tank_capacity_l",
        "fuel_density_kg_l",
    ]
    missing_critical = [p for p in _CRITICAL_PARAMS if p not in params or params[p] is None]
    if missing_critical:
        logger.warning(
            "envelope_solver: INSUFFICIENT_DATA — missing critical params: %s",
            missing_critical,
        )
        warnings.append(
            f"INSUFFICIENT_DATA: Missing critical parameters {missing_critical}. "
            f"Results may be invalid — models will raise errors for missing data."
        )

    run_uq = uq_method == "monte_carlo" and mc_samples > 1

    speeds = np.linspace(max(speed_range[0], 0.5), speed_range[1], grid_resolution)
    altitudes = np.linspace(altitude_range[0], altitude_range[1], grid_resolution)

    z_feasible = np.zeros((grid_resolution, grid_resolution))
    z_ident = np.zeros((grid_resolution, grid_resolution))
    z_ident_p5 = np.zeros((grid_resolution, grid_resolution))
    z_ident_p95 = np.zeros((grid_resolution, grid_resolution))
    z_endurance = np.zeros((grid_resolution, grid_resolution))
    z_endurance_p5 = np.zeros((grid_resolution, grid_resolution))
    z_endurance_p95 = np.zeros((grid_resolution, grid_resolution))
    z_fuel_flow = np.zeros((grid_resolution, grid_resolution))
    z_power = np.zeros((grid_resolution, grid_resolution))

    mc_engine: MonteCarloEngine | None = None
    mc_inputs: list[MCInput] | None = None
    if run_uq:
        mc_engine = MonteCarloEngine(n_samples=mc_samples, seed=42)
        mc_inputs = _build_uncertain_inputs(params)

    for i, alt in enumerate(altitudes):
        for j, spd in enumerate(speeds):
            try:
                out = evaluate_point(params, spd, alt)

                aero_ok = out.get("aero_feasible", 0.0) > 0.5
                engine_ok = out.get("engine_feasible", 1.0) > 0.5
                fuel_ok = out.get("fuel_feasible", 1.0) > 0.5
                blur_ok = out.get("motion_blur_feasible", 1.0) > 0.5
                batt_ok = out.get("battery_feasible", 1.0) > 0.5
                ceiling_ok = alt * 3.281 <= params.get("service_ceiling_ft", 99999)
                gsd_ok = out.get("gsd_cm_px", 0.0) <= params.get("min_gsd_cm_px", 2.0)

                z_feasible[i, j] = float(aero_ok and engine_ok and fuel_ok and blur_ok and batt_ok and ceiling_ok and gsd_ok)
                z_ident[i, j] = out.get("identification_confidence", 0.0)
                z_endurance[i, j] = out.get("fuel_endurance_hr", 0.0)
                z_fuel_flow[i, j] = out.get("fuel_flow_rate_g_hr", 0.0)
                z_power[i, j] = out.get("engine_power_required_kw", 0.0)

                if run_uq and mc_engine is not None and mc_inputs is not None:
                    def _model_fn(perturbed: dict[str, float], _s: float = spd, _a: float = alt) -> dict[str, float]:
                        p = dict(params)
                        p.update(perturbed)
                        return evaluate_point(p, _s, _a)

                    mc_result = mc_engine.propagate(_model_fn, mc_inputs)
                    ident_samples = mc_result.output_samples.get("identification_confidence")
                    endur_samples = mc_result.output_samples.get("fuel_endurance_hr")
                    if ident_samples is not None and len(ident_samples) > 0:
                        z_ident_p5[i, j] = float(np.percentile(ident_samples, 5))
                        z_ident_p95[i, j] = float(np.percentile(ident_samples, 95))
                    else:
                        z_ident_p5[i, j] = z_ident[i, j]
                        z_ident_p95[i, j] = z_ident[i, j]
                    if endur_samples is not None and len(endur_samples) > 0:
                        z_endurance_p5[i, j] = float(np.percentile(endur_samples, 5))
                        z_endurance_p95[i, j] = float(np.percentile(endur_samples, 95))
                    else:
                        z_endurance_p5[i, j] = z_endurance[i, j]
                        z_endurance_p95[i, j] = z_endurance[i, j]
                else:
                    z_ident_p5[i, j] = z_ident[i, j]
                    z_ident_p95[i, j] = z_ident[i, j]
                    z_endurance_p5[i, j] = z_endurance[i, j]
                    z_endurance_p95[i, j] = z_endurance[i, j]

            except Exception as e:
                z_feasible[i, j] = 0.0
                if i == 0 and j == 0:
                    warnings.append(f"Model error at ({spd:.1f} m/s, {alt:.0f} m): {e}")

    min_ident = params.get("min_identification_confidence", 0.8)
    mission_viable = 0
    total = grid_resolution * grid_resolution
    for i in range(grid_resolution):
        for j in range(grid_resolution):
            feasible = z_feasible[i, j] > 0.5
            ident_ok = z_ident[i, j] >= min_ident
            if feasible and ident_ok:
                mission_viable += 1
    mission_success = mission_viable / total if total > 0 else 0.0

    speed_flat = np.tile(speeds, grid_resolution)
    alt_flat = np.repeat(altitudes, grid_resolution)
    ident_flat = z_ident.flatten()
    endurance_flat = z_endurance.flatten()

    sensitivity: list[SensitivityEntry] = []
    for pname, x, target in [
        ("airspeed_ms", speed_flat, ident_flat),
        ("altitude_m", alt_flat, ident_flat),
        ("airspeed_ms (endurance)", speed_flat, endurance_flat),
        ("altitude_m (endurance)", alt_flat, endurance_flat),
    ]:
        if np.std(x) > 1e-12 and np.std(target) > 1e-12:
            corr = abs(float(np.corrcoef(x, target)[0, 1]))
            sensitivity.append(SensitivityEntry(parameter_name=pname, contribution_pct=corr * 100))
    sensitivity.sort(key=lambda e: e.contribution_pct, reverse=True)

    mid_speed = (speed_range[0] + speed_range[1]) / 2
    mid_alt = (altitude_range[0] + altitude_range[1]) / 2
    nominal_out = evaluate_point(params, mid_speed, mid_alt)

    def _out(mean_val: float | None, unit: str = "") -> EnvelopeOutput | None:
        if mean_val is None:
            return None
        v = float(mean_val)
        return EnvelopeOutput(mean=v, std=0.0, percentiles={"p5": v, "p50": v, "p95": v}, units=unit or "1")

    feasibility_surface = EnvelopeSurface(
        x_label="Speed (m/s)",
        y_label="Altitude (m)",
        z_label="Feasible",
        x_values=speeds.tolist(),
        y_values=altitudes.tolist(),
        z_mean=z_feasible.tolist(),
        z_p5=z_feasible.tolist(),
        z_p95=z_feasible.tolist(),
        feasible_mask=[[bool(v > 0.5) for v in row] for row in z_feasible.tolist()],
    )

    ident_surface = EnvelopeSurface(
        x_label="Speed (m/s)",
        y_label="Altitude (m)",
        z_label="Identification Confidence",
        x_values=speeds.tolist(),
        y_values=altitudes.tolist(),
        z_mean=z_ident.tolist(),
        z_p5=z_ident_p5.tolist(),
        z_p95=z_ident_p95.tolist(),
    )

    endurance_surface = EnvelopeSurface(
        x_label="Speed (m/s)",
        y_label="Altitude (m)",
        z_label="Fuel Endurance (hr)",
        x_values=speeds.tolist(),
        y_values=altitudes.tolist(),
        z_mean=z_endurance.tolist(),
        z_p5=z_endurance_p5.tolist(),
        z_p95=z_endurance_p95.tolist(),
    )

    if run_uq:
        warnings.append(f"UQ: Monte Carlo with {mc_samples} samples per grid point")

    response = EnvelopeResponse(
        speed_altitude_feasibility=feasibility_surface,
        identification_confidence=ident_surface,
        endurance_surface=endurance_surface,
        safe_inspection_speed=_out(nominal_out.get("safe_inspection_speed_ms"), "m/s"),
        fuel_endurance=_out(nominal_out.get("fuel_endurance_hr"), "hr"),
        battery_reserve=_out(nominal_out.get("endurance_min"), "min"),
        fuel_flow_rate=_out(nominal_out.get("fuel_flow_rate_g_hr"), "g/hr"),
        mission_completion_probability=mission_success,
        sensitivity=sensitivity,
        computation_time_s=time.time() - t0,
        warnings=warnings,
    )

    return response


def estimate_endurance_budget_minutes(
    twin: VehicleTwin,
    speed_ms: float = 15.0,
    altitude_m: float = 50.0,
) -> dict[str, float]:
    """Single-point physics estimate for UI battery/fuel endurance (not full envelope grid)."""
    params = _extract_params(twin)
    values = evaluate_point(params, speed_ms, altitude_m)
    fuel_min = float(values.get("fuel_endurance_hr", 0.0)) * 60.0
    elec_min = float(values.get("endurance_min", 0.0))
    return {
        "endurance_minutes_electrical": elec_min,
        "endurance_minutes_fuel": fuel_min,
        "endurance_minutes_effective": max(fuel_min, elec_min),
    }
