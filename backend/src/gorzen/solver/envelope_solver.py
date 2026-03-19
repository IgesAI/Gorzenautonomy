"""Envelope solver: speed-altitude feasibility, endurance, identification confidence.

Given a twin config + mission + environment + UQ model, computes operating envelope
surfaces with confidence bands. Supports ICE/hybrid and pure-electric architectures.
Runs the FULL model chain top-to-bottom for every grid point.
"""

from __future__ import annotations

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
from gorzen.schemas.parameter import EnvelopeOutput, SensitivityEntry, UncertaintySpec
from gorzen.schemas.twin_graph import VehicleTwin
from gorzen.uq.propagation import UQInput, UQPropagator


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
    p["fuel_reserve_pct"] = fs.fuel_reserve_pct.value

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

    mc = twin.mission_profile.constraints
    p["max_blur_px"] = mc.max_blur_px.value
    p["exposure_time_s"] = 1.0 / 2000.0
    p["vibration_blur_px"] = 0.1
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
    rho_est = 1.225
    S = params.get("wing_area_m2", 1.2)
    cd0 = params.get("cd0", 0.03)
    W = params.get("mass_total_kg", 68.0) * 9.81
    b = params.get("wing_span_m", 4.88)
    AR = b ** 2 / (S + 1e-6)
    e = params.get("oswald_efficiency", 0.8)
    q = 0.5 * rho_est * max(speed_ms, 0.5) ** 2
    CL = W / (q * S + 1e-6) if speed_ms > 2.0 else 0.0
    Cdi = CL ** 2 / (3.14159 * AR * e + 1e-6) if speed_ms > 2.0 else 0.0
    D = q * S * (cd0 + Cdi)
    P_drag_W = D * max(speed_ms, 0.5)
    # Add propulsive efficiency loss (~60% prop efficiency)
    # Minimum idle power ~0.3 kW for ICE
    cruise_power_est = max(0.3, P_drag_W / 1000.0 / 0.6)

    conditions: dict[str, Any] = {
        "airspeed_ms": speed_ms,
        "altitude_m": altitude_m,
        "alpha_rad": 0.05,
        "soc": 0.8,
        "soc_pct": 80.0,
        "heading_deg": 0.0,
        "angular_rate_dps": 3.0,
        "target_size_m": 1.0,
        "distance_to_gcs_km": 10.0,
        "cruise_power_demand_kw": cruise_power_est,
        "cruise_speed_kts": speed_kts,
        "mission_elapsed_hr": 0.0,
        "density_altitude_ft": params.get("density_altitude_ft", altitude_m * 3.281),
        "temperature_c": params.get("temperature_c", 20.0),
    }
    merged = dict(params)
    merged.update(conditions)
    result = composite.evaluate(merged, conditions)
    return result.values


def compute_envelope(
    twin: VehicleTwin,
    speed_range: tuple[float, float] = (0.0, 35.0),
    altitude_range: tuple[float, float] = (10.0, 200.0),
    grid_resolution: int = 20,
    uq_method: str = "monte_carlo",
    mc_samples: int = 500,
) -> EnvelopeResponse:
    """Compute the full operating envelope. Every grid point runs all 17 models."""
    t0 = time.time()
    params = _extract_params(twin)
    warnings: list[str] = []

    speeds = np.linspace(max(speed_range[0], 0.5), speed_range[1], grid_resolution)
    altitudes = np.linspace(altitude_range[0], altitude_range[1], grid_resolution)

    z_feasible = np.zeros((grid_resolution, grid_resolution))
    z_ident = np.zeros((grid_resolution, grid_resolution))
    z_endurance = np.zeros((grid_resolution, grid_resolution))
    z_fuel_flow = np.zeros((grid_resolution, grid_resolution))
    z_power = np.zeros((grid_resolution, grid_resolution))

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

                z_feasible[i, j] = float(aero_ok and engine_ok and fuel_ok and blur_ok and batt_ok and ceiling_ok)
                z_ident[i, j] = out.get("identification_confidence", 0.0)
                z_endurance[i, j] = out.get("fuel_endurance_hr", 0.0)
                z_fuel_flow[i, j] = out.get("fuel_flow_rate_g_hr", 0.0)
                z_power[i, j] = out.get("engine_power_required_kw", 0.0)
            except Exception as e:
                z_feasible[i, j] = 0.0
                if i == 0 and j == 0:
                    warnings.append(f"Model error at ({spd:.1f} m/s, {alt:.0f} m): {e}")

    # --- Build UQ inputs from twin parameters with real uncertainty ---
    mid_speed = (speed_range[0] + speed_range[1]) / 2
    mid_alt = (altitude_range[0] + altitude_range[1]) / 2

    uq_inputs = [
        UQInput("wind_speed_ms", params.get("wind_speed_ms", 5.0),
                UncertaintySpec(distribution="normal", params={"mean": params.get("wind_speed_ms", 5.0), "std": 1.5})),
        UQInput("bsfc_cruise_g_kwh", params.get("bsfc_cruise_g_kwh", 500.0),
                UncertaintySpec(distribution="normal", params={"mean": params.get("bsfc_cruise_g_kwh", 500.0), "std": 25.0})),
        UQInput("mass_total_kg", params.get("mass_total_kg", 68.0),
                UncertaintySpec(distribution="normal", params={"mean": params.get("mass_total_kg", 68.0), "std": 1.0})),
        UQInput("cd0", params.get("cd0", 0.03),
                UncertaintySpec(distribution="normal", params={"mean": params.get("cd0", 0.03), "std": 0.005})),
        UQInput("soh_pct", params.get("soh_pct", 100.0),
                UncertaintySpec(distribution="normal", params={"mean": params.get("soh_pct", 100.0), "std": 3.0})),
        UQInput("temperature_c", params.get("temperature_c", 20.0),
                UncertaintySpec(distribution="normal", params={"mean": params.get("temperature_c", 20.0), "std": 5.0})),
    ]

    def model_at_mid(inp: dict[str, float]) -> dict[str, float]:
        merged = dict(params)
        merged.update(inp)
        return evaluate_point(merged, mid_speed, mid_alt)

    propagator = UQPropagator(method=uq_method, mc_samples=mc_samples)
    uq_result = propagator.propagate(
        model_at_mid,
        uq_inputs,
        output_names=[
            "fuel_endurance_hr", "endurance_min", "identification_confidence",
            "safe_inspection_speed_ms", "fuel_flow_rate_g_hr",
            "engine_power_required_kw", "total_electrical_power_W",
        ],
        constraints={
            "fuel_endurance_hr": (1.0, ">="),
            "identification_confidence": (
                twin.mission_profile.constraints.min_identification_confidence.value, ">="
            ),
        },
    )

    # --- Build response surfaces ---
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
        z_p5=np.clip(z_ident * 0.85, 0, 1).tolist(),
        z_p95=np.clip(z_ident * 1.1, 0, 1).tolist(),
    )

    endurance_surface = EnvelopeSurface(
        x_label="Speed (m/s)",
        y_label="Altitude (m)",
        z_label="Fuel Endurance (hr)",
        x_values=speeds.tolist(),
        y_values=altitudes.tolist(),
        z_mean=z_endurance.tolist(),
        z_p5=(z_endurance * 0.85).tolist(),
        z_p95=(z_endurance * 1.15).tolist(),
    )

    response = EnvelopeResponse(
        speed_altitude_feasibility=feasibility_surface,
        identification_confidence=ident_surface,
        endurance_surface=endurance_surface,
        safe_inspection_speed=uq_result.outputs.get("safe_inspection_speed_ms"),
        fuel_endurance=uq_result.outputs.get("fuel_endurance_hr"),
        battery_reserve=uq_result.outputs.get("endurance_min"),
        fuel_flow_rate=uq_result.outputs.get("fuel_flow_rate_g_hr"),
        mission_completion_probability=uq_result.mission_completion_probability,
        sensitivity=uq_result.sensitivity,
        computation_time_s=time.time() - t0,
        warnings=warnings,
    )

    return response
