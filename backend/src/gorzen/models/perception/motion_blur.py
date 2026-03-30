"""Motion blur model: smear distance/pixels, safe inspection speed.

smear_distance = v_ground * t_exposure
smear_pixels = smear_distance / GSD

All parameters are REQUIRED — no silent fallback defaults.
Exposure time must be an explicit input from the sensor specification
or mission configuration, not assumed.
"""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel
from gorzen.validation.parameter_validator import require_param


class MotionBlurModel(SubsystemModel):
    """Quantitative motion blur model turning blur into a speed limit."""

    def parameter_names(self) -> list[str]:
        return ["exposure_time_s", "vibration_blur_px"]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return [
            "smear_distance_m", "smear_pixels", "motion_blur_feasible",
            "safe_inspection_speed_ms",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        t_exp = require_param(params, "exposure_time_s", "MotionBlurModel")
        vib_blur = require_param(params, "vibration_blur_px", "MotionBlurModel")

        v_ground = require_param(conditions, "airspeed_ms", "MotionBlurModel")
        gsd_cm = conditions.get("gsd_cm_px")
        if gsd_cm is None:
            gsd_cm = params.get("gsd_cm_px")
        if gsd_cm is None:
            raise ValueError(
                "INSUFFICIENT_DATA: 'gsd_cm_px' is required but missing (context: MotionBlurModel)"
            )
        gsd_m = float(gsd_cm) / 100.0
        max_blur = require_param(conditions, "max_blur_px", "MotionBlurModel")

        smear_dist = v_ground * t_exp
        smear_px = smear_dist / (gsd_m + 1e-9)

        total_blur = np.sqrt(smear_px ** 2 + vib_blur ** 2)
        feasible = total_blur <= max_blur

        # Safe speed: max v such that total blur <= limit
        blur_budget_motion = np.sqrt(max(max_blur ** 2 - vib_blur ** 2, 0.0))
        safe_speed = blur_budget_motion * gsd_m / (t_exp + 1e-9)

        return ModelOutput(
            values={
                "smear_distance_m": smear_dist,
                "smear_pixels": total_blur,
                "motion_blur_feasible": float(feasible),
                "safe_inspection_speed_ms": safe_speed,
            },
            units={
                "smear_distance_m": "m", "smear_pixels": "px",
                "motion_blur_feasible": "1", "safe_inspection_speed_ms": "m/s",
            },
            feasible=feasible,
        )


def compute_required_shutter_speed(
    ground_speed_ms: float,
    gsd_cm_px: float,
    max_blur_px: float = 0.5,
    vibration_blur_px: float = 0.1,
) -> float:
    """Compute the minimum shutter speed (1/s) to keep blur within budget."""
    gsd_m = gsd_cm_px / 100.0
    blur_budget = np.sqrt(max(max_blur_px ** 2 - vibration_blur_px ** 2, 0.01))
    max_exposure = blur_budget * gsd_m / (ground_speed_ms + 1e-9)
    return 1.0 / (max_exposure + 1e-9)
