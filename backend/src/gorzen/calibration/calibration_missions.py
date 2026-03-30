"""Calibration mission definitions: first-class mission types for twin refinement.

Each calibration mission is a structured procedure that produces specific
observables for model parameter calibration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CalibrationMissionType(str, Enum):
    HOVER_POWER_SWEEP = "hover_power_sweep"
    SPEED_SWEEP = "speed_sweep"
    LATENCY_TEST = "latency_test"
    VIBRATION_CHARACTERIZATION = "vibration_characterization"
    ROLLING_SHUTTER_CALIBRATION = "rolling_shutter_calibration"


@dataclass
class CalibrationStep:
    """A single step in a calibration mission procedure."""

    step_id: int
    description: str
    duration_s: float
    setpoints: dict[str, float] = field(default_factory=dict)
    observables: list[str] = field(default_factory=list)
    acceptance_criteria: dict[str, tuple[float, float]] = field(default_factory=dict)


@dataclass
class CalibrationMissionDef:
    """Definition of a calibration mission."""

    mission_type: CalibrationMissionType
    name: str
    description: str
    steps: list[CalibrationStep] = field(default_factory=list)
    required_conditions: dict[str, str] = field(default_factory=dict)
    calibrates_parameters: list[str] = field(default_factory=list)
    estimated_duration_min: float = 0.0


def hover_power_sweep() -> CalibrationMissionDef:
    """Hover power sweep: SoC vs current draw, motor heating.

    Measures power consumption at various throttle levels in stable hover
    to calibrate the propulsion efficiency and battery discharge models.
    """
    steps = []
    for i, throttle_pct in enumerate([50, 60, 70, 80, 90, 100]):
        steps.append(
            CalibrationStep(
                step_id=i,
                description=f"Hover at {throttle_pct}% throttle for 30s",
                duration_s=30.0,
                setpoints={"throttle_pct": throttle_pct, "altitude_m": 10.0},
                observables=[
                    "battery_voltage_v",
                    "battery_current_a",
                    "motor_rpm",
                    "motor_temperature_c",
                    "altitude_m",
                    "battery_soc_pct",
                ],
                acceptance_criteria={
                    "altitude_variance_m": (0.0, 1.0),
                    "wind_speed_ms": (0.0, 3.0),
                },
            )
        )

    return CalibrationMissionDef(
        mission_type=CalibrationMissionType.HOVER_POWER_SWEEP,
        name="Hover Power Sweep",
        description="Measures power consumption at multiple throttle levels in stable hover",
        steps=steps,
        required_conditions={"wind": "< 3 m/s", "battery_soc": "> 80%"},
        calibrates_parameters=[
            "prop_ct_static",
            "prop_cp_static",
            "motor_resistance_ohm",
            "internal_resistance_mohm",
        ],
        estimated_duration_min=5.0,
    )


def forward_flight_speed_sweep() -> CalibrationMissionDef:
    """Forward-flight speed sweep: drag/power curve.

    Flies at multiple speeds to map the power-vs-speed curve for drag model calibration.
    """
    steps = []
    for i, speed in enumerate([5, 8, 12, 16, 20, 25, 30]):
        steps.append(
            CalibrationStep(
                step_id=i,
                description=f"Cruise at {speed} m/s for 60s",
                duration_s=60.0,
                setpoints={"airspeed_ms": speed, "altitude_m": 50.0},
                observables=[
                    "battery_voltage_v",
                    "battery_current_a",
                    "airspeed_ms",
                    "ground_speed_ms",
                    "wind_speed_ms",
                    "altitude_m",
                ],
                acceptance_criteria={
                    "speed_variance_ms": (0.0, 1.0),
                    "altitude_variance_m": (0.0, 2.0),
                },
            )
        )

    return CalibrationMissionDef(
        mission_type=CalibrationMissionType.SPEED_SWEEP,
        name="Forward Flight Speed Sweep",
        description="Maps power-vs-speed curve for drag and propulsion model calibration",
        steps=steps,
        required_conditions={"wind": "< 5 m/s", "battery_soc": "> 70%"},
        calibrates_parameters=["cd0", "oswald_efficiency", "prop_ct_static", "prop_cp_static"],
        estimated_duration_min=10.0,
    )


def latency_test() -> CalibrationMissionDef:
    """Step-response latency tests: camera -> encode -> inference pipeline."""
    steps = [
        CalibrationStep(
            step_id=0,
            description="Capture calibration target at hover, measure pipeline latency",
            duration_s=30.0,
            setpoints={"altitude_m": 20.0, "airspeed_ms": 0.0},
            observables=[
                "capture_timestamp_us",
                "encode_complete_us",
                "inference_complete_us",
                "detection_result",
            ],
        ),
        CalibrationStep(
            step_id=1,
            description="Capture at cruise speed, measure latency under motion",
            duration_s=30.0,
            setpoints={"altitude_m": 30.0, "airspeed_ms": 10.0},
            observables=[
                "capture_timestamp_us",
                "encode_complete_us",
                "inference_complete_us",
                "detection_result",
                "frame_drop_count",
            ],
        ),
    ]

    return CalibrationMissionDef(
        mission_type=CalibrationMissionType.LATENCY_TEST,
        name="Pipeline Latency Test",
        description="Measures end-to-end capture-to-detection latency",
        steps=steps,
        required_conditions={"calibration_target": "visible"},
        calibrates_parameters=["inference_latency_ms", "max_throughput_fps"],
        estimated_duration_min=3.0,
    )


def vibration_characterization() -> CalibrationMissionDef:
    """Vibration characterization: IMU + camera blur proxy."""
    steps = []
    for i, rpm_pct in enumerate([50, 70, 90, 100]):
        steps.append(
            CalibrationStep(
                step_id=i,
                description=f"Hover at {rpm_pct}% RPM, record IMU + image sharpness",
                duration_s=20.0,
                setpoints={"throttle_pct": rpm_pct, "altitude_m": 10.0},
                observables=[
                    "imu_accel_rms_mg",
                    "imu_gyro_rms_dps",
                    "image_sharpness_score",
                    "vibration_frequency_hz",
                ],
            )
        )

    return CalibrationMissionDef(
        mission_type=CalibrationMissionType.VIBRATION_CHARACTERIZATION,
        name="Vibration Characterization",
        description="Maps vibration amplitude vs RPM for blur model calibration",
        steps=steps,
        required_conditions={"wind": "< 3 m/s"},
        calibrates_parameters=["vibration_blur_px"],
        estimated_duration_min=3.0,
    )


def rolling_shutter_calibration() -> CalibrationMissionDef:
    """Rolling shutter calibration: readout time measurement."""
    steps = [
        CalibrationStep(
            step_id=0,
            description="Fly past vertical edge at known speed, measure RS skew",
            duration_s=30.0,
            setpoints={"airspeed_ms": 15.0, "altitude_m": 20.0},
            observables=[
                "ground_speed_ms",
                "image_rs_skew_px",
                "measured_readout_time_ms",
            ],
        ),
        CalibrationStep(
            step_id=1,
            description="Repeat at higher speed for validation",
            duration_s=30.0,
            setpoints={"airspeed_ms": 25.0, "altitude_m": 20.0},
            observables=[
                "ground_speed_ms",
                "image_rs_skew_px",
                "measured_readout_time_ms",
            ],
        ),
    ]

    return CalibrationMissionDef(
        mission_type=CalibrationMissionType.ROLLING_SHUTTER_CALIBRATION,
        name="Rolling Shutter Calibration",
        description="Measures actual sensor readout time from RS artifacts",
        steps=steps,
        required_conditions={"calibration_edge_target": "available"},
        calibrates_parameters=["readout_time_ms"],
        estimated_duration_min=3.0,
    )


ALL_CALIBRATION_MISSIONS = {
    CalibrationMissionType.HOVER_POWER_SWEEP: hover_power_sweep,
    CalibrationMissionType.SPEED_SWEEP: forward_flight_speed_sweep,
    CalibrationMissionType.LATENCY_TEST: latency_test,
    CalibrationMissionType.VIBRATION_CHARACTERIZATION: vibration_characterization,
    CalibrationMissionType.ROLLING_SHUTTER_CALIBRATION: rolling_shutter_calibration,
}
