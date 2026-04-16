"""GIQE-based image quality model: MTF, SNR, compression, blur composite.

Uses GIQE (General Image Quality Equation) concepts to compute an internal
image-utility scalar that can be propagated under uncertainty.
"""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel
from gorzen.validation.parameter_validator import require_param


class ImageQualityModel(SubsystemModel):
    """GIQE-inspired composite image quality model.

    NIIRS ~ c0 + c1*log10(GSD) + c2*log10(RER) + c3*G/SNR + c4*H
    where RER = relative edge response (MTF proxy), G = noise gain, H = overshoot height.

    Simplified for digital-twin use: combines GSD, system MTF, SNR, blur, compression.
    """

    # LITERATURE: GIQE-5 standard coefficients
    # Reference: Griffith, "Updated GIQE", ASPRS/JACIE 2012-2014; NGA publications
    # NIIRS = c0 + c1*ln(GSD) + c2*ln(RER) + c3*(G/SNR) + c4*H
    # Uses natural log (ln) per GIQE 5 formulation
    GIQE_C0 = 9.57
    GIQE_C1 = -3.32  # GSD term (inches, natural log)
    GIQE_C2 = 3.32  # RER term (unified, no bifurcation)
    GIQE_C3 = -1.9  # noise gain / SNR term (G/SNR)
    GIQE_C4 = -2.0  # edge overshoot H (refined for sharpening artifacts)

    def parameter_names(self) -> list[str]:
        return [
            "lens_mtf_nyquist",
            "pixel_size_um",
            "jpeg_quality",
            "encoding_bitrate_mbps",
            "min_gsd_cm_px",
        ]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return [
            "system_mtf",
            "snr_db",
            "compression_quality",
            "image_utility_score",
            "niirs_equivalent",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        lens_mtf = require_param(params, "lens_mtf_nyquist", "ImageQualityModel")
        pixel_um = require_param(params, "pixel_size_um", "ImageQualityModel")
        jpeg_q = require_param(params, "jpeg_quality", "ImageQualityModel")

        gsd_cm = require_param(conditions, "gsd_cm_px", "ImageQualityModel")
        blur_px = require_param(conditions, "smear_pixels", "ImageQualityModel")
        light_lux = require_param(conditions, "ambient_light_lux_out", "ImageQualityModel")
        compression_qf = require_param(
            conditions, "compression_quality_factor", "ImageQualityModel"
        )

        # System MTF: lens * sampling * motion blur degradation.
        # LITERATURE: the sampling MTF for a square pixel aperture is
        # sinc(0.5) = 2/pi ≈ 0.6366. Computed exactly rather than rounded.
        sampling_mtf = float(np.sinc(0.5))
        blur_mtf = np.sinc(blur_px * 0.5) if blur_px > 0 else 1.0
        blur_mtf = max(blur_mtf, 0.05)
        system_mtf = lens_mtf * sampling_mtf * blur_mtf

        # RER approximation from system MTF. Anything > ~0.9 triggers edge
        # overshoot when the image pipeline sharpens.
        rer = 0.5 + 0.5 * system_mtf

        # SNR model (photon noise + read noise). ``read_noise_e`` can be
        # overridden per sensor when calibrated data exist; otherwise we use
        # a conservative generic 3 e-.
        read_noise = float(params.get("sensor_read_noise_e", 3.0))
        signal = pixel_um**2 * light_lux * 0.001
        snr = signal / (np.sqrt(signal + read_noise**2) + 1e-6)
        snr_db = 20 * np.log10(snr + 1e-6)

        # HEURISTIC: requires sensor-specific calibration
        comp_q = min(jpeg_q, compression_qf) / 100.0
        compression_mtf = 0.7 + 0.3 * comp_q

        effective_mtf = system_mtf * compression_mtf

        # Edge overshoot H (GIQE-5). Models sharpening-induced ringing; when
        # the twin exposes a post-processing sharpening gain we use the
        # classic H = 0.2*(G-1) approximation from NGA's 2006 technote,
        # otherwise assume no sharpening (H = 0).
        G = float(params.get("post_processing_sharpening_gain", 1.0))
        H = max(0.0, 0.2 * (G - 1.0))

        # GIQE 5: NIIRS = c0 + c1*ln(GSD_in) + c2*ln(RER) + c3*(G/SNR) + c4*H
        # GSD must be in inches; uses natural log (ln).
        gsd_inches = gsd_cm / 2.54  # cm -> inches
        niirs = (
            self.GIQE_C0
            + self.GIQE_C1 * np.log(gsd_inches + 1e-9)
            + self.GIQE_C2 * np.log(rer + 1e-9)
            + self.GIQE_C3 * (G / (snr + 1e-6))
            + self.GIQE_C4 * H
        )
        niirs = np.clip(niirs, 0.0, 9.0)

        # Task-relative GSD utility: smooth sigmoid degradation as GSD approaches
        # the mission's required resolution. Captures altitude-driven quality loss.
        min_gsd = require_param(params, "min_gsd_cm_px", "ImageQualityModel")
        gsd_ratio = gsd_cm / (min_gsd + 1e-9)
        # HEURISTIC: task GSD utility curve tuning
        gsd_factor = 1.0 / (1.0 + np.exp(6.0 * (gsd_ratio - 0.85)))

        # Blend NIIRS quality with GSD task-relevance
        niirs_quality = min(niirs / 7.0, 1.0)
        utility = float(niirs_quality * gsd_factor)

        return ModelOutput(
            values={
                "system_mtf": effective_mtf,
                "snr_db": snr_db,
                "compression_quality": comp_q,
                "image_utility_score": utility,
                "niirs_equivalent": niirs,
            },
            units={
                "system_mtf": "1",
                "snr_db": "dB",
                "compression_quality": "1",
                "image_utility_score": "1",
                "niirs_equivalent": "NIIRS",
            },
        )
