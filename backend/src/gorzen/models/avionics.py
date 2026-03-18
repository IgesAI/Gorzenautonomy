"""Avionics model: EKF navigation performance, GPS/RTK, geotag accuracy."""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel


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
        gps_type = str(params.get("gps_type", "rtk"))
        ekf_pos = params.get("ekf_position_noise_m", 0.5)
        ekf_vel = params.get("ekf_velocity_noise_ms", 0.1)
        gyro_noise = params.get("imu_gyro_noise_dps", 0.005)
        accel_noise = params.get("imu_accel_noise_mg", 0.4)
        baro_noise = params.get("baro_noise_m", 1.0)

        gps_noise = self.GPS_NOISE.get(gps_type, 2.5)

        # Fused position uncertainty (simplified Kalman steady-state)
        pos_unc = np.sqrt(gps_noise ** 2 + ekf_pos ** 2)

        # Velocity from GPS + IMU integration
        vel_unc = np.sqrt((gps_noise * 0.1) ** 2 + ekf_vel ** 2)

        # Heading uncertainty from gyro integration + magnetometer
        heading_unc = gyro_noise * 10.0 + 0.5  # simplified

        # Altitude: baro + GPS fusion
        alt_unc = np.sqrt(baro_noise ** 2 + (gps_noise * 1.5) ** 2) * 0.5

        # Geotag error: position + timing + attitude contribution
        v = conditions.get("airspeed_ms", 10.0)
        timing_error_s = 0.01
        geotag_pos = pos_unc
        geotag_timing = v * timing_error_s
        alt = conditions.get("altitude_m", 50.0)
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
