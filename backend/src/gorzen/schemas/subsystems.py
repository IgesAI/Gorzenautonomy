"""Layer 2: Domain-specific subsystem schemas for the VTOL digital twin.

Designed to be hardware-agnostic while covering the full parameter space needed
for ICE-powered, hybrid, and pure-electric lift+cruise VTOL platforms (including
Cobra AERO engines and Vertical Autonomy airframes).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from gorzen.schemas.parameter import TypedParameter, UncertaintySpec, param


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class FlightMode(str, Enum):
    HOVER = "hover"
    TRANSITION = "transition"
    CRUISE = "cruise"


class ShutterType(str, Enum):
    ROLLING = "rolling"
    GLOBAL = "global"


class AutopilotType(str, Enum):
    PX4 = "px4"
    ARDUPILOT = "ardupilot"
    PICCOLO = "piccolo"
    CUSTOM = "custom"


class GpsType(str, Enum):
    L1 = "l1"
    L1_L2 = "l1_l2"
    RTK = "rtk"
    PPK = "ppk"


class BatteryChemistry(str, Enum):
    LIPO = "lipo"
    LI_ION = "li_ion"
    LIHV = "lihv"
    SOLID_STATE = "solid_state"


class ESCType(str, Enum):
    PWM = "pwm"
    DSHOT = "dshot"
    FOC = "foc"


class WindModel(str, Enum):
    DRYDEN = "dryden"
    VON_KARMAN = "von_karman"
    STEADY = "steady"


class EngineType(str, Enum):
    TWO_STROKE_SINGLE = "2stroke_single"
    TWO_STROKE_TWIN = "2stroke_twin"
    TWO_STROKE_TRIPLE = "2stroke_triple"
    FOUR_STROKE = "4stroke"
    WANKEL = "wankel"
    ELECTRIC = "electric"


class CoolingType(str, Enum):
    AIR_COOLED = "air_cooled"
    LIQUID_COOLED = "liquid_cooled"


class FuelType(str, Enum):
    GASOLINE = "gasoline"
    JP5 = "jp5"
    JP8 = "jp8"
    JET_A = "jet_a"
    VP_HEAVY_FUEL = "vp_heavy_fuel"
    AVGAS = "avgas"


class PowerArchitecture(str, Enum):
    PURE_ICE = "pure_ice"
    PARALLEL_HYBRID = "parallel_hybrid"
    SERIES_HYBRID = "series_hybrid"
    PURE_ELECTRIC = "pure_electric"


class CommsMode(str, Enum):
    MANET = "manet"
    SATCOM = "satcom"
    DIRECT_LINK = "direct_link"
    LTE = "lte"


class PayloadMountLocation(str, Enum):
    NOSE = "nose"
    BOOM = "boom"
    BELLY = "belly"
    WING = "wing"
    INTERNAL_BAY = "internal_bay"


# ---------------------------------------------------------------------------
# Subsystem schemas
# ---------------------------------------------------------------------------

class AirframeConfig(BaseModel):
    """Airframe: mass, dimensions, aero coefficients, structural and operational limits."""

    # Dimensions
    wing_span_m: TypedParameter = param(4.88, "m", min_value=0.5, max_value=20, group="dimensions", display_name="Wingspan")
    fuselage_length_m: TypedParameter = param(2.49, "m", min_value=0.3, max_value=10, group="dimensions", display_name="Length")
    height_m: TypedParameter = param(0.66, "m", min_value=0.1, max_value=5, group="dimensions", display_name="Height")
    wing_area_m2: TypedParameter = param(1.2, "m2", min_value=0.01, max_value=20, group="aero", display_name="Wing Area")

    # Mass properties
    mass_empty_kg: TypedParameter = param(34.0, "kg", min_value=0.5, max_value=500, group="mass", display_name="Empty Weight")
    mass_mtow_kg: TypedParameter = param(68.0, "kg", min_value=1.0, max_value=1000, group="mass", display_name="Max Gross Weight")
    payload_capacity_nose_kg: TypedParameter = param(11.3, "kg", min_value=0, max_value=100, group="mass", display_name="Payload Capacity (Nose)")
    payload_capacity_boom_kg: TypedParameter = param(4.53, "kg", min_value=0, max_value=50, group="mass", display_name="Payload Capacity (Booms)")
    fuel_capacity_kg: TypedParameter = param(15.0, "kg", min_value=0, max_value=200, group="mass", display_name="Fuel Capacity")
    cg_x_m: TypedParameter = param(0.0, "m", group="mass", display_name="CG X-offset", advanced=True)
    cg_z_m: TypedParameter = param(0.0, "m", group="mass", display_name="CG Z-offset", advanced=True)

    # Aero coefficients
    cd0: TypedParameter = param(0.03, "1", min_value=0.005, max_value=0.2, group="aero", display_name="Parasitic Drag Coeff", advanced=True)
    cl_alpha: TypedParameter = param(5.0, "1/rad", min_value=1.0, max_value=8.0, group="aero", display_name="Lift-Curve Slope", advanced=True)
    oswald_efficiency: TypedParameter = param(0.8, "1", min_value=0.5, max_value=1.0, group="aero", display_name="Oswald Efficiency", advanced=True)

    # Performance limits
    max_speed_kts: TypedParameter = param(65.0, "kts", min_value=20, max_value=250, group="performance", display_name="VNE")
    cruise_speed_kts: TypedParameter = param(42.0, "kts", min_value=10, max_value=200, group="performance", display_name="Cruise Speed")
    service_ceiling_ft: TypedParameter = param(18000, "ft", min_value=0, max_value=50000, group="performance", display_name="Service Ceiling")
    vtol_ceiling_ft: TypedParameter = param(9000, "ft", min_value=0, max_value=30000, group="performance", display_name="VTOL Ceiling")
    max_endurance_hr: TypedParameter = param(12.0, "hr", min_value=0.1, max_value=48, group="performance", display_name="Max Endurance")
    range_nmi: TypedParameter = param(675.0, "nmi", min_value=1, max_value=5000, group="performance", display_name="Range")

    # Structural / operational limits
    max_load_factor: TypedParameter = param(3.0, "1", min_value=1.5, max_value=6.0, group="structural", display_name="Max Load Factor")
    max_crosswind_kts: TypedParameter = param(30.0, "kts", min_value=0, max_value=60, group="structural", display_name="Max Crosswind")
    max_operating_temp_c: TypedParameter = param(49.0, "degC", min_value=0, max_value=70, group="environment", display_name="Max Operating Temp")
    min_operating_temp_c: TypedParameter = param(-29.0, "degC", min_value=-60, max_value=20, group="environment", display_name="Min Operating Temp")
    landing_zone_m: TypedParameter = param(7.62, "m", min_value=1, max_value=50, group="vtol", display_name="Landing Zone Size")

    # Crew / logistics
    crew_size: TypedParameter = param(2, "1", min_value=1, max_value=10, group="logistics", display_name="Crew Size")


class LiftPropulsionConfig(BaseModel):
    """Lift propulsion group: electric rotors for VTOL hover/transition."""

    rotor_count: TypedParameter = param(4, "1", min_value=1, max_value=12, group="rotor", display_name="Rotor Count")
    rotor_diameter_m: TypedParameter = param(0.6, "m", min_value=0.1, max_value=3.0, group="rotor", display_name="Rotor Diameter")
    blade_count: TypedParameter = param(2, "1", min_value=2, max_value=6, group="rotor", display_name="Blade Count")
    motor_kv: TypedParameter = param(400.0, "rpm/V", min_value=50, max_value=5000, group="motor", display_name="Motor Kv")
    motor_resistance_ohm: TypedParameter = param(0.05, "ohm", min_value=0.001, max_value=1.0, group="motor", display_name="Motor Resistance", advanced=True)
    motor_kt: TypedParameter = param(0.024, "N.m/A", min_value=0.001, max_value=1.0, group="motor", display_name="Motor Kt", advanced=True)
    esc_type: TypedParameter = param("foc", "1", group="esc", display_name="ESC Protocol")
    prop_ct_static: TypedParameter = param(0.1, "1", min_value=0.01, max_value=0.3, group="prop", display_name="CT Static", advanced=True)
    prop_cp_static: TypedParameter = param(0.04, "1", min_value=0.005, max_value=0.15, group="prop", display_name="CP Static", advanced=True)


class CruisePropulsionConfig(BaseModel):
    """Cruise propulsion: ICE engine, propeller, or electric pusher.

    Supports 2-stroke singles, inline triples, and electric pushers.
    """

    # Power architecture
    power_architecture: TypedParameter = param("pure_ice", "1", group="architecture", display_name="Power Architecture")

    # ICE engine parameters
    engine_type: TypedParameter = param("2stroke_single", "1", group="engine", display_name="Engine Type")
    displacement_cc: TypedParameter = param(33.0, "cc", min_value=0, max_value=1000, group="engine", display_name="Displacement")
    engine_mass_kg: TypedParameter = param(3.15, "kg", min_value=0, max_value=50, group="engine", display_name="Engine System Mass")
    max_power_kw: TypedParameter = param(2.2, "kW", min_value=0, max_value=100, group="engine", display_name="Max Power Output")
    max_power_rpm: TypedParameter = param(8350, "rpm", min_value=0, max_value=20000, group="engine", display_name="Max Power RPM")
    bsfc_cruise_g_kwh: TypedParameter = param(500.0, "g/kW-hr", min_value=100, max_value=1500, group="engine", display_name="BSFC (Cruise)")
    cooling_type: TypedParameter = param("air_cooled", "1", group="engine", display_name="Cooling Type")

    # Fuel injection / management
    efi_system: TypedParameter = param("intelliject", "1", group="efi", display_name="EFI System")
    altitude_compensation: TypedParameter = param(True, "1", group="efi", display_name="Altitude Compensation")
    cold_start_compensation: TypedParameter = param(True, "1", group="efi", display_name="Cold Start Comp.")

    # Preheat
    preheat_required: TypedParameter = param(False, "1", group="startup", display_name="Preheat Required")
    preheat_time_min: TypedParameter = param(0.0, "min", min_value=0, max_value=30, group="startup", display_name="Preheat Time")
    preheat_power_w: TypedParameter = param(0.0, "W", min_value=0, max_value=500, group="startup", display_name="Preheat Power")

    # Propeller
    cruise_prop_diameter_m: TypedParameter = param(0.6, "m", min_value=0.1, max_value=2.0, group="prop", display_name="Cruise Prop Diameter")
    cruise_prop_pitch_in: TypedParameter = param(10.0, "in", min_value=2, max_value=30, group="prop", display_name="Cruise Prop Pitch", advanced=True)

    # Generator (for hybrid or series-hybrid)
    generator_output_w: TypedParameter = param(200.0, "W", min_value=0, max_value=10000, group="generator", display_name="Generator Output (Continuous)")
    generator_output_intermittent_w: TypedParameter = param(400.0, "W", min_value=0, max_value=20000, group="generator", display_name="Generator Output (Intermittent)")
    generator_voltage_v: TypedParameter = param(28.0, "V", min_value=0, max_value=100, group="generator", display_name="Generator Voltage")

    # Hybrid boost
    hybrid_boost_available: TypedParameter = param(True, "1", group="hybrid", display_name="Parallel Hybrid Boost")
    hybrid_boost_power_kw: TypedParameter = param(0.5, "kW", min_value=0, max_value=50, group="hybrid", display_name="Hybrid Boost Power")

    # Telemetry / data
    engine_can_interface: TypedParameter = param(True, "1", group="interface", display_name="CAN Interface")
    engine_serial_interface: TypedParameter = param(True, "1", group="interface", display_name="Serial Interface")
    onboard_data_logging: TypedParameter = param(True, "1", group="interface", display_name="Onboard Data Logging")

    # Sensors available from ECU
    sensor_cht: TypedParameter = param(True, "1", group="sensors", display_name="CHT Sensor", advanced=True)
    sensor_mat: TypedParameter = param(True, "1", group="sensors", display_name="MAT Sensor", advanced=True)
    sensor_fuel_pressure: TypedParameter = param(True, "1", group="sensors", display_name="Fuel Pressure Sensor", advanced=True)
    sensor_baro: TypedParameter = param(True, "1", group="sensors", display_name="Baro Sensor", advanced=True)
    sensor_map: TypedParameter = param(True, "1", group="sensors", display_name="MAP Sensor", advanced=True)


class FuelSystemConfig(BaseModel):
    """Fuel system: tank, fuel type, consumption model, reserves."""

    fuel_type: TypedParameter = param("jp5", "1", group="fuel", display_name="Fuel Type")
    fuel_density_kg_l: TypedParameter = param(0.81, "kg/L", min_value=0.6, max_value=1.0, group="fuel", display_name="Fuel Density")
    tank_capacity_l: TypedParameter = param(18.5, "L", min_value=0.1, max_value=500, group="tank", display_name="Tank Capacity")
    tank_capacity_kg: TypedParameter = param(15.0, "kg", min_value=0.1, max_value=400, group="tank", display_name="Tank Capacity (mass)")
    usable_fuel_pct: TypedParameter = param(95.0, "%", min_value=80, max_value=100, group="tank", display_name="Usable Fuel %")
    fuel_reserve_pct: TypedParameter = param(15.0, "%", min_value=5, max_value=40, group="policy", display_name="Fuel Reserve")
    premix_ratio: TypedParameter = param(50.0, "1", min_value=20, max_value=100, group="fuel", display_name="Premix Ratio (fuel:oil)")

    # Self-priming pump
    fuel_pump_self_priming: TypedParameter = param(True, "1", group="pump", display_name="Self-Priming Pump")
    fuel_pump_type: TypedParameter = param("currawong", "1", group="pump", display_name="Fuel Pump")
    fuel_pressure_accumulator: TypedParameter = param(True, "1", group="pump", display_name="Pressure Accumulator")


class EnergyConfig(BaseModel):
    """Electrical energy subsystem: battery for VTOL motors, avionics, payloads.

    In ICE/hybrid architectures the battery handles VTOL lift motors and avionics;
    in pure-electric it is the sole energy source.
    """

    chemistry: TypedParameter = param("lipo", "1", group="battery", display_name="Chemistry")
    cell_count_s: TypedParameter = param(12, "1", min_value=1, max_value=48, group="battery", display_name="Cells in Series")
    cell_count_p: TypedParameter = param(2, "1", min_value=1, max_value=20, group="battery", display_name="Cells in Parallel")
    capacity_ah: TypedParameter = param(16.0, "Ah", min_value=0.1, max_value=200, group="battery", display_name="Capacity")
    nominal_voltage_v: TypedParameter = param(44.4, "V", min_value=3.0, max_value=200, group="battery", display_name="Nominal Voltage")
    internal_resistance_mohm: TypedParameter = param(10.0, "mohm", min_value=1, max_value=500, group="battery", display_name="Internal Resistance")
    soh_pct: TypedParameter = param(
        100.0, "%", min_value=50, max_value=100, group="health", display_name="State of Health",
        uncertainty=UncertaintySpec(distribution="normal", params={"mean": 100.0, "std": 3.0}),
    )
    wiring_loss_mohm: TypedParameter = param(5.0, "mohm", min_value=0, max_value=100, group="wiring", display_name="Wiring Resistance", advanced=True)
    reserve_policy_pct: TypedParameter = param(20.0, "%", min_value=5, max_value=50, group="policy", display_name="Battery Reserve Policy")

    # Generator charging (from ICE engine generator)
    generator_charge_available: TypedParameter = param(True, "1", group="charging", display_name="Generator Charging")
    generator_charge_rate_w: TypedParameter = param(200.0, "W", min_value=0, max_value=5000, group="charging", display_name="Generator Charge Rate")


class AvionicsConfig(BaseModel):
    """Avionics: autopilot, sensors, navigation filter configuration."""

    autopilot_type: TypedParameter = param("piccolo", "1", group="autopilot", display_name="Autopilot")
    gps_type: TypedParameter = param("rtk", "1", group="nav", display_name="GPS Type")
    imu_gyro_noise_dps: TypedParameter = param(0.005, "deg/s/sqrt(Hz)", group="imu", display_name="Gyro Noise Density", advanced=True)
    imu_accel_noise_mg: TypedParameter = param(0.4, "mg/sqrt(Hz)", group="imu", display_name="Accel Noise Density", advanced=True)
    ekf_position_noise_m: TypedParameter = param(0.5, "m", min_value=0.01, max_value=10, group="nav", display_name="EKF Position Noise", advanced=True)
    ekf_velocity_noise_ms: TypedParameter = param(0.1, "m/s", min_value=0.01, max_value=5, group="nav", display_name="EKF Velocity Noise", advanced=True)
    baro_noise_m: TypedParameter = param(1.0, "m", min_value=0.1, max_value=10, group="nav", display_name="Baro Noise", advanced=True)
    mag_available: TypedParameter = param(True, "1", group="nav", display_name="Magnetometer Available")
    moving_baseline_capable: TypedParameter = param(True, "1", group="nav", display_name="Moving Baseline Capable")


class ComputeConfig(BaseModel):
    """Onboard compute: SoC, accelerator, thermal throttling, inference latency."""

    soc_model: TypedParameter = param("jetson_orin_nano", "1", group="compute", display_name="SoC Model")
    accelerator_type: TypedParameter = param("gpu", "1", group="compute", display_name="Accelerator")
    max_power_w: TypedParameter = param(15.0, "W", min_value=1, max_value=100, group="compute", display_name="Max Power Draw")
    thermal_throttle_temp_c: TypedParameter = param(85.0, "degC", min_value=50, max_value=120, group="thermal", display_name="Throttle Temperature", advanced=True)
    inference_latency_ms: TypedParameter = param(30.0, "ms", min_value=1, max_value=1000, group="inference", display_name="Inference Latency")
    max_throughput_fps: TypedParameter = param(30.0, "Hz", min_value=1, max_value=120, group="inference", display_name="Max Throughput")


class CommsConfig(BaseModel):
    """Communications: MANET, SATCOM, direct link, link budget, QoS."""

    # Primary radio (MANET)
    primary_comms_mode: TypedParameter = param("manet", "1", group="primary", display_name="Primary Comms")
    manet_range_nmi: TypedParameter = param(75.0, "nmi", min_value=1, max_value=500, group="manet", display_name="MANET Range")
    manet_frequency_mhz: TypedParameter = param(1350.0, "MHz", min_value=100, max_value=6000, group="manet", display_name="MANET Frequency", advanced=True)
    manet_bandwidth_mbps: TypedParameter = param(10.0, "Mbps", min_value=0.01, max_value=100, group="manet", display_name="MANET Bandwidth")

    # SATCOM
    satcom_available: TypedParameter = param(True, "1", group="satcom", display_name="SATCOM Available")
    satcom_bandwidth_mbps: TypedParameter = param(2.0, "Mbps", min_value=0.01, max_value=50, group="satcom", display_name="SATCOM Bandwidth")
    satcom_latency_ms: TypedParameter = param(600.0, "ms", min_value=50, max_value=5000, group="satcom", display_name="SATCOM Latency")

    # Link budget basics
    tx_power_dbm: TypedParameter = param(30.0, "dBm", min_value=0, max_value=50, group="link", display_name="TX Power")
    antenna_gain_dbi: TypedParameter = param(5.0, "dBi", min_value=-5, max_value=25, group="link", display_name="Antenna Gain")
    receiver_sensitivity_dbm: TypedParameter = param(-100.0, "dBm", min_value=-120, max_value=-50, group="link", display_name="Rx Sensitivity", advanced=True)

    # C2 and data QoS
    required_c2_latency_ms: TypedParameter = param(200.0, "ms", min_value=10, max_value=5000, group="qos", display_name="C2 Max Latency")
    required_video_latency_ms: TypedParameter = param(500.0, "ms", min_value=50, max_value=10000, group="qos", display_name="Video Max Latency")


class PayloadConfig(BaseModel):
    """Payload: camera, lens, gimbal, encoding, mount location."""

    # Mounting
    mount_location: TypedParameter = param("nose", "1", group="mount", display_name="Mount Location")
    payload_mass_kg: TypedParameter = param(5.0, "kg", min_value=0, max_value=50, group="mount", display_name="Payload Mass")
    payload_type: TypedParameter = param("eo_ir_gimbal", "1", group="mount", display_name="Payload Type")

    # Camera / sensor
    sensor_width_mm: TypedParameter = param(13.2, "mm", min_value=1, max_value=50, group="sensor", display_name="Sensor Width")
    sensor_height_mm: TypedParameter = param(8.8, "mm", min_value=1, max_value=50, group="sensor", display_name="Sensor Height")
    focal_length_mm: TypedParameter = param(24.0, "mm", min_value=2, max_value=500, group="lens", display_name="Focal Length")
    pixel_width: TypedParameter = param(4000, "px", min_value=100, max_value=20000, group="sensor", display_name="Pixel Width")
    pixel_height: TypedParameter = param(3000, "px", min_value=100, max_value=20000, group="sensor", display_name="Pixel Height")
    pixel_size_um: TypedParameter = param(3.3, "um", min_value=0.5, max_value=15, group="sensor", display_name="Pixel Size", advanced=True)
    shutter_type: TypedParameter = param("rolling", "1", group="shutter", display_name="Shutter Type")
    readout_time_ms: TypedParameter = param(30.0, "ms", min_value=0, max_value=200, group="shutter", display_name="Readout Time")
    lens_mtf_nyquist: TypedParameter = param(0.3, "1", min_value=0.05, max_value=0.9, group="lens", display_name="Lens MTF @ Nyquist", advanced=True)

    # IR capability
    has_ir: TypedParameter = param(True, "1", group="ir", display_name="IR Sensor Available")
    ir_resolution_px: TypedParameter = param(640, "px", min_value=0, max_value=4096, group="ir", display_name="IR Resolution")

    # Gimbal
    gimbal_stabilized: TypedParameter = param(True, "1", group="gimbal", display_name="Gimbal Stabilized")
    gimbal_pitch_range_deg: TypedParameter = param(180.0, "deg", min_value=0, max_value=360, group="gimbal", display_name="Gimbal Pitch Range")
    gimbal_yaw_continuous: TypedParameter = param(True, "1", group="gimbal", display_name="Continuous Yaw")

    # Encoding / storage
    codec: TypedParameter = param("h265", "1", group="encoding", display_name="Video Codec")
    encoding_bitrate_mbps: TypedParameter = param(8.0, "Mbps", min_value=0.1, max_value=200, group="encoding", display_name="Encoding Bitrate")
    jpeg_quality: TypedParameter = param(90, "1", min_value=1, max_value=100, group="encoding", display_name="JPEG Quality")
    onboard_storage_gb: TypedParameter = param(256, "GB", min_value=0, max_value=4096, group="storage", display_name="Onboard Storage")

    # SAR / SIGINT (optional payload types referenced in datasheets)
    sar_capable: TypedParameter = param(False, "1", group="special", display_name="SAR Capable")
    sigint_capable: TypedParameter = param(False, "1", group="special", display_name="SIGINT Capable")
    comms_relay_capable: TypedParameter = param(False, "1", group="special", display_name="Comms Relay Capable")


class AIModelConfig(BaseModel):
    """Onboard AI/VLM model configuration and calibration."""

    model_config = {"protected_namespaces": ()}

    model_artifact_id: TypedParameter = param("yolov8n", "1", group="model", display_name="Model Artifact")
    runtime: TypedParameter = param("tensorrt", "1", group="model", display_name="Runtime")
    input_resolution_px: TypedParameter = param(640, "px", min_value=64, max_value=4096, group="model", display_name="Input Resolution")
    accuracy_at_nominal: TypedParameter = param(0.85, "1", min_value=0.0, max_value=1.0, group="performance", display_name="mAP @ Nominal")
    accuracy_degradation_per_blur_px: TypedParameter = param(0.07, "1/px", min_value=0.0, max_value=1.0, group="performance", display_name="Accuracy Drop per Blur px", advanced=True)
    accuracy_degradation_per_jpeg_q10: TypedParameter = param(0.05, "1/10q", min_value=0.0, max_value=0.5, group="performance", display_name="Accuracy Drop per JPEG Q/10", advanced=True)
    ood_threshold: TypedParameter = param(0.7, "1", min_value=0.0, max_value=1.0, group="reliability", display_name="OOD Detection Threshold", advanced=True)


class EnvironmentConfig(BaseModel):
    """Mission environment: wind, lighting, temperature, density altitude."""

    wind_model: TypedParameter = param("dryden", "1", group="wind", display_name="Turbulence Model")
    wind_speed_ms: TypedParameter = param(5.0, "m/s", min_value=0, max_value=40, group="wind", display_name="Mean Wind Speed")
    gust_intensity: TypedParameter = param("moderate", "1", group="wind", display_name="Gust Intensity")
    wind_direction_deg: TypedParameter = param(0.0, "deg", min_value=0, max_value=360, group="wind", display_name="Wind Direction")
    temperature_c: TypedParameter = param(20.0, "degC", min_value=-40, max_value=60, group="atmosphere", display_name="Temperature")
    pressure_hpa: TypedParameter = param(1013.25, "hPa", min_value=800, max_value=1100, group="atmosphere", display_name="Pressure")
    density_altitude_ft: TypedParameter = param(0, "ft", min_value=-2000, max_value=25000, group="atmosphere", display_name="Density Altitude")
    ambient_light_lux: TypedParameter = param(10000.0, "lux", min_value=0, max_value=120000, group="lighting", display_name="Ambient Light")


class MissionConstraints(BaseModel):
    """Operator-specified mission constraints."""

    min_gsd_cm_px: TypedParameter = param(2.0, "cm/px", min_value=0.1, max_value=50, group="perception", display_name="Min GSD")
    max_blur_px: TypedParameter = param(0.5, "px", min_value=0.1, max_value=5, group="perception", display_name="Max Blur")
    min_identification_confidence: TypedParameter = param(0.8, "1", min_value=0.0, max_value=1.0, group="perception", display_name="Min ID Confidence")
    fuel_reserve_pct: TypedParameter = param(15.0, "%", min_value=5, max_value=40, group="energy", display_name="Fuel Reserve")
    battery_reserve_pct: TypedParameter = param(20.0, "%", min_value=5, max_value=50, group="energy", display_name="Battery Reserve")
    min_overlap_pct: TypedParameter = param(70.0, "%", min_value=0, max_value=95, group="mapping", display_name="Min Image Overlap")
    max_mission_duration_hr: TypedParameter = param(8.0, "hr", min_value=0.1, max_value=48, group="general", display_name="Max Duration")
    max_range_nmi: TypedParameter = param(300.0, "nmi", min_value=1, max_value=2000, group="general", display_name="Max Range")


class MissionProfileConfig(BaseModel):
    """Combined mission profile: environment + waypoints + constraints."""

    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    constraints: MissionConstraints = Field(default_factory=MissionConstraints)
    waypoints: list[dict] = Field(default_factory=list)
    mission_type: str = "isr"
