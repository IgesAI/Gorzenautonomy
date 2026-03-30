"""Rolling shutter distortion model and risk scoring.

Rolling shutter exposes sensor lines sequentially, causing skew/wobble
proportional to velocity and angular rate during readout.
"""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel
from gorzen.validation.parameter_validator import require_param


class RollingShutterModel(SubsystemModel):
    """Rolling-shutter distortion risk model.

    Computes image-plane displacement from RS readout during motion.
    Global shutter cameras have readout_time_ms = 0 and produce zero distortion.
    """

    def parameter_names(self) -> list[str]:
        return [
            "shutter_type",
            "readout_time_ms",
            "pixel_height",
            "sensor_height_mm",
            "focal_length_mm",
        ]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return [
            "rs_skew_px",
            "rs_wobble_px",
            "rs_total_distortion_px",
            "rs_risk_score",
            "rs_feasible",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        if "shutter_type" not in params or params["shutter_type"] is None:
            raise ValueError(
                "INSUFFICIENT_DATA: 'shutter_type' is required but missing"
                " (context: RollingShutterModel)"
            )
        shutter = str(params["shutter_type"])
        readout_ms = require_param(params, "readout_time_ms", "RollingShutterModel")
        px_h = require_param(params, "pixel_height", "RollingShutterModel")
        sh_mm = require_param(params, "sensor_height_mm", "RollingShutterModel")
        fl_mm = require_param(params, "focal_length_mm", "RollingShutterModel")

        v_ground = require_param(conditions, "airspeed_ms", "RollingShutterModel")
        gsd_m = require_param(conditions, "gsd_cm_px", "RollingShutterModel") / 100.0
        angular_rate_dps = require_param(conditions, "angular_rate_dps", "RollingShutterModel")
        max_blur = require_param(conditions, "max_blur_px", "RollingShutterModel")

        if shutter == "global" or readout_ms <= 0:
            return ModelOutput(
                values={
                    "rs_skew_px": 0.0,
                    "rs_wobble_px": 0.0,
                    "rs_total_distortion_px": 0.0,
                    "rs_risk_score": 0.0,
                    "rs_feasible": 1.0,
                },
                units={
                    "rs_skew_px": "px",
                    "rs_wobble_px": "px",
                    "rs_total_distortion_px": "px",
                    "rs_risk_score": "1",
                    "rs_feasible": "1",
                },
            )

        t_readout = readout_ms / 1000.0

        # Skew: lateral displacement across full frame due to translational motion
        ground_travel_during_readout = v_ground * t_readout
        skew_px = ground_travel_during_readout / (gsd_m + 1e-9)

        # Wobble: angular_rate × readout_time × focal_length_px (per Phase One/Pix4D)
        angular_rate_rps = np.radians(angular_rate_dps)
        focal_length_px = (fl_mm / (sh_mm + 1e-9)) * px_h if sh_mm > 0 else px_h
        wobble_rad = angular_rate_rps * t_readout
        wobble_px = wobble_rad * focal_length_px

        total = np.sqrt(skew_px**2 + wobble_px**2)

        # Risk score: 0 = no risk, 1 = exceeds budget by 2x+
        risk = min(total / (max_blur + 1e-6), 2.0) / 2.0
        # HEURISTIC: RS budget is typically 2x motion blur budget
        feasible = total <= max_blur * 2.0

        return ModelOutput(
            values={
                "rs_skew_px": skew_px,
                "rs_wobble_px": wobble_px,
                "rs_total_distortion_px": total,
                "rs_risk_score": risk,
                "rs_feasible": float(feasible),
            },
            units={
                "rs_skew_px": "px",
                "rs_wobble_px": "px",
                "rs_total_distortion_px": "px",
                "rs_risk_score": "1",
                "rs_feasible": "1",
            },
            feasible=feasible,
        )
