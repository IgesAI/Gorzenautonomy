"""Identification confidence model: degradation-aware, OOD monitoring, compression sensitivity.

Does NOT rely solely on softmax confidence — includes degradation distance and
system-level factors.
"""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel


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
        acc_nominal = params.get("accuracy_at_nominal", 0.85)
        deg_per_blur = params.get("accuracy_degradation_per_blur_px", 0.15)
        deg_per_q10 = params.get("accuracy_degradation_per_jpeg_q10", 0.05)
        ood_thresh = params.get("ood_threshold", 0.7)
        input_res = params.get("input_resolution_px", 640)

        blur_px = conditions.get("smear_pixels", 0.0)
        rs_distortion = conditions.get("rs_total_distortion_px", 0.0)
        jpeg_q = conditions.get("jpeg_quality", 90)
        comp_qf = conditions.get("compression_quality_factor", 90.0)
        pot = conditions.get("pixels_on_target", 50.0)
        latency_ms = conditions.get("effective_latency_ms", 30.0)
        image_utility = conditions.get("image_utility_score", 0.7)

        # Blur penalty: combined motion + RS
        total_blur = np.sqrt(blur_px ** 2 + (rs_distortion * 0.5) ** 2)
        blur_penalty = min(total_blur * deg_per_blur, 0.5)

        # Compression penalty: JPEG quality + bandwidth-limited quality
        effective_q = min(jpeg_q, comp_qf)
        q_deficit = max(0, 90 - effective_q) / 10.0
        compression_penalty = min(q_deficit * deg_per_q10, 0.3)

        # Pixel density factor: degrade if target has too few pixels
        min_useful_pixels = input_res * 0.1
        if pot >= min_useful_pixels:
            pixel_density_factor = 1.0
        elif pot > 5:
            pixel_density_factor = pot / min_useful_pixels
        else:
            pixel_density_factor = 0.1

        # Latency penalty: frame staleness
        latency_penalty = min(latency_ms / 1000.0 * 0.1, 0.1)

        # Degradation score: distance from nominal operating regime
        degradation_score = blur_penalty + compression_penalty + (1.0 - pixel_density_factor) * 0.3 + latency_penalty
        degradation_score = min(degradation_score, 1.0)

        # OOD risk: probability that inputs are outside training distribution
        ood_risk = degradation_score / (ood_thresh + 1e-6)
        ood_risk = min(ood_risk, 1.0)

        # Final identification confidence
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
        )
