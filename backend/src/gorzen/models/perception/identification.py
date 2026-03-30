"""Identification confidence model: degradation-aware, OOD monitoring, compression sensitivity.

Does NOT rely solely on softmax confidence — includes degradation distance and
system-level factors.
"""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel
from gorzen.validation.parameter_validator import require_param


class IdentificationConfidenceModel(SubsystemModel):
    """Computes P(identification_success | conditions).

    Combines:
    - Degradation-aware monitor score (OOD / degradation distance)
    - Predicted pixel density and blur
    - Expected compression level and bandwidth conditions
    - Measured inference latency and frame rate
    """

    def parameter_names(self) -> list[str]:
        return [
            "accuracy_at_nominal", "accuracy_degradation_per_blur_px",
            "accuracy_degradation_per_jpeg_q10", "ood_threshold",
            "input_resolution_px",
        ]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return [
            "identification_confidence", "degradation_score",
            "pixel_density_factor", "blur_penalty",
            "compression_penalty", "latency_penalty",
            "ood_risk",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        acc_nominal = require_param(params, "accuracy_at_nominal", "IdentificationConfidenceModel")
        deg_per_blur = require_param(params, "accuracy_degradation_per_blur_px", "IdentificationConfidenceModel")
        deg_per_q10 = require_param(params, "accuracy_degradation_per_jpeg_q10", "IdentificationConfidenceModel")
        ood_thresh = require_param(params, "ood_threshold", "IdentificationConfidenceModel")
        input_res = require_param(params, "input_resolution_px", "IdentificationConfidenceModel")

        blur_px = require_param(conditions, "smear_pixels", "IdentificationConfidenceModel")
        rs_distortion = require_param(conditions, "rs_total_distortion_px", "IdentificationConfidenceModel")
        jpeg_q = require_param(conditions, "jpeg_quality", "IdentificationConfidenceModel")
        comp_qf = require_param(conditions, "compression_quality_factor", "IdentificationConfidenceModel")
        pot = require_param(conditions, "pixels_on_target", "IdentificationConfidenceModel")
        latency_ms = require_param(conditions, "effective_latency_ms", "IdentificationConfidenceModel")
        image_utility = require_param(conditions, "image_utility_score", "IdentificationConfidenceModel")

        # HEURISTIC: requires model-specific benchmark calibration
        # RS weighted at 1% since it's correctable; cap to avoid dominating at high speed
        rs_contribution = min(rs_distortion * 0.01, 0.5)
        total_blur = np.sqrt(blur_px ** 2 + rs_contribution ** 2)
        # HEURISTIC: requires model-specific benchmark calibration
        blur_penalty = min(total_blur * deg_per_blur, 0.5)

        # HEURISTIC: requires model-specific benchmark calibration
        effective_q = min(jpeg_q, comp_qf)
        q_deficit = max(0, 90 - effective_q) / 10.0
        compression_penalty = min(q_deficit * deg_per_q10, 0.3)

        # HEURISTIC: Johnson-criteria-inspired breakpoints
        PIXELS_EXCELLENT = 8.0
        PIXELS_DETECT = 3.0
        PIXELS_MINIMUM = 1.0

        if pot >= PIXELS_EXCELLENT:
            pixel_density_factor = 1.0
        elif pot >= PIXELS_DETECT:
            pixel_density_factor = 0.5 + 0.5 * (pot - PIXELS_DETECT) / (PIXELS_EXCELLENT - PIXELS_DETECT)
        elif pot >= PIXELS_MINIMUM:
            pixel_density_factor = 0.15 * (pot - PIXELS_MINIMUM) / (PIXELS_DETECT - PIXELS_MINIMUM)
        else:
            pixel_density_factor = 0.0

        # HEURISTIC: requires model-specific benchmark calibration
        latency_penalty = min(latency_ms / 1000.0 * 0.1, 0.1)

        # HEURISTIC: requires model-specific benchmark calibration
        degradation_score = blur_penalty + compression_penalty + (1.0 - pixel_density_factor) * 0.3 + latency_penalty
        degradation_score = min(degradation_score, 1.0)

        ood_risk = degradation_score / (ood_thresh + 1e-6)
        ood_risk = min(ood_risk, 1.0)

        confidence = acc_nominal * pixel_density_factor * (1.0 - blur_penalty) * (1.0 - compression_penalty) * (1.0 - latency_penalty)
        confidence *= image_utility
        confidence = np.clip(confidence, 0.0, 1.0)

        return ModelOutput(
            values={
                "identification_confidence": confidence,
                "degradation_score": degradation_score,
                "pixel_density_factor": pixel_density_factor,
                "blur_penalty": blur_penalty,
                "compression_penalty": compression_penalty,
                "latency_penalty": latency_penalty,
                "ood_risk": ood_risk,
            },
            units={
                "identification_confidence": "1",
                "degradation_score": "1",
                "pixel_density_factor": "1",
                "blur_penalty": "1",
                "compression_penalty": "1",
                "latency_penalty": "1",
                "ood_risk": "1",
            },
            warnings=[
                "HEURISTIC_PROXY: identification confidence is a heuristic proxy, "
                "not calibrated operational confidence",
            ],
        )
