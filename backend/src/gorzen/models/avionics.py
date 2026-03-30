"""Avionics model: EKF navigation performance, GPS/RTK, geotag accuracy."""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel
from gorzen.validation.parameter_validator import require_param


class AvionicsModel(SubsystemModel):
    """Models navigation filter performance bounds and geotag accuracy.

    Position/velocity uncertainty as function of sensor suite and GPS mode.
    """

    GPS_NOISE = {
        "l1": 2.5,
        "l1_l2": 1.5,
        "rtk": 0.02,
        "ppk": 0.01,
    }

    def parameter_names(self) -> list[str]:
        return [
            "gps_type", "ekf_position_noise_m", "ekf_velocity_noise_ms",
            "imu_gyro_noise_dps", "imu_accel_noise_mg", "baro_noise_m",
        ]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return [
            "position_uncertainty_m", "velocity_uncertainty_ms",
            "heading_uncertainty_deg", "geotag_error_m",
            "altitude_uncertainty_m",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        gps_type = str(require_param(params, "gps_type", "AvionicsModel"))
        ekf_pos = require_param(params, "ekf_position_noise_m", "AvionicsModel")
        ekf_vel = require_param(params, "ekf_velocity_noise_ms", "AvionicsModel")
        gyro_noise = require_param(params, "imu_gyro_noise_dps", "AvionicsModel")
        baro_noise = require_param(params, "baro_noise_m", "AvionicsModel")

        if gps_type not in self.GPS_NOISE:
            raise ValueError(
                f"AvionicsModel: unknown gps_type '{gps_type}', "
                f"must be one of {list(self.GPS_NOISE.keys())}"
            )
        gps_noise = self.GPS_NOISE[gps_type]

        # Fused position uncertainty (simplified Kalman steady-state)
        pos_unc = np.sqrt(gps_noise ** 2 + ekf_pos ** 2)

        # Velocity from GPS + IMU integration
        vel_unc = np.sqrt((gps_noise * 0.1) ** 2 + ekf_vel ** 2)

        # Heading uncertainty from gyro integration + magnetometer
        heading_unc = gyro_noise * 10.0 + 0.5  # simplified

        # Altitude: baro + GPS fusion
        alt_unc = np.sqrt(baro_noise ** 2 + (gps_noise * 1.5) ** 2) * 0.5

        # Geotag error: position + timing + attitude contribution
        v = require_param(conditions, "airspeed_ms", "AvionicsModel")
        timing_error_s = 0.01  # HEURISTIC: requires sensor-specific calibration
        geotag_pos = pos_unc
        geotag_timing = v * timing_error_s
        alt = require_param(conditions, "altitude_m", "AvionicsModel")
        geotag_attitude = alt * np.radians(heading_unc) * 0.1
        geotag_error = np.sqrt(geotag_pos ** 2 + geotag_timing ** 2 + geotag_attitude ** 2)

        return ModelOutput(
            values={
                "position_uncertainty_m": pos_unc,
                "velocity_uncertainty_ms": vel_unc,
                "heading_uncertainty_deg": heading_unc,
                "geotag_error_m": geotag_error,
                "altitude_uncertainty_m": alt_unc,
            },
            units={
                "position_uncertainty_m": "m", "velocity_uncertainty_ms": "m/s",
                "heading_uncertainty_deg": "deg", "geotag_error_m": "m",
                "altitude_uncertainty_m": "m",
            },
        )
