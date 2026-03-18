"""GIQE-based image quality model: MTF, SNR, compression, blur composite.

Uses GIQE (General Image Quality Equation) concepts to compute an internal
image-utility scalar that can be propagated under uncertainty.
"""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel


class ImageQualityModel(SubsystemModel):
    """GIQE-inspired composite image quality model.

    NIIRS ~ c0 + c1*log10(GSD) + c2*log10(RER) + c3*G/SNR + c4*H
    where RER = relative edge response (MTF proxy), G = noise gain, H = overshoot height.

    Simplified for digital-twin use: combines GSD, system MTF, SNR, blur, compression.
    """

    GIQE_C0 = 10.251
    GIQE_C1 = -3.32
    GIQE_C2 = 3.32
    GIQE_C3 = -1.559
    GIQE_C4 = -0.334

    def parameter_names(self) -> list[str]:
        return [
            "lens_mtf_nyquist", "pixel_size_um",
            "jpeg_quality", "encoding_bitrate_mbps",
        ]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return [
            "system_mtf", "snr_db", "compression_quality",
            "image_utility_score", "niirs_equivalent",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        lens_mtf = params.get("lens_mtf_nyquist", 0.3)
        pixel_um = params.get("pixel_size_um", 3.3)
        jpeg_q = params.get("jpeg_quality", 90)
        encoding_br = params.get("encoding_bitrate_mbps", 20.0)

        gsd_cm = conditions.get("gsd_cm_px", 1.0)
        blur_px = conditions.get("smear_pixels", 0.0)
        light_lux = conditions.get("ambient_light_lux_out", 10000.0)
        compression_qf = conditions.get("compression_quality_factor", 90.0)

        # System MTF: lens * sampling * motion blur degradation
        sampling_mtf = 0.64  # sinc(0.5) for square pixels
        blur_mtf = np.sinc(blur_px * 0.5) if blur_px > 0 else 1.0
        blur_mtf = max(blur_mtf, 0.05)
        system_mtf = lens_mtf * sampling_mtf * blur_mtf

        # RER approximation from system MTF
        rer = 0.5 + 0.5 * system_mtf

        # SNR model (simplified: photon noise + read noise)
        # Higher light = higher SNR
        signal = pixel_um ** 2 * light_lux * 0.001  # relative signal
        read_noise = 3.0  # electrons equivalent
        snr = signal / (np.sqrt(signal + read_noise ** 2) + 1e-6)
        snr_db = 20 * np.log10(snr + 1e-6)

        # Compression quality: blend between JPEG quality and bandwidth-limited quality
        comp_q = min(jpeg_q, compression_qf) / 100.0
        compression_mtf = 0.7 + 0.3 * comp_q

        effective_mtf = system_mtf * compression_mtf

        # GIQE-like score
        gsd_m = gsd_cm / 100.0
        niirs = (
            self.GIQE_C0
            + self.GIQE_C1 * np.log10(gsd_m + 1e-9)
            + self.GIQE_C2 * np.log10(rer + 1e-9)
            + self.GIQE_C3 * (1.0 / (snr + 1e-6))
        )
        niirs = np.clip(niirs, 0.0, 9.0)

        # Image utility score normalized 0-1
        utility = niirs / 9.0

        return ModelOutput(
            values={
                "system_mtf": effective_mtf,
                "snr_db": snr_db,
                "compression_quality": comp_q,
                "image_utility_score": utility,
                "niirs_equivalent": niirs,
            },
            units={
                "system_mtf": "1", "snr_db": "dB",
                "compression_quality": "1",
                "image_utility_score": "1", "niirs_equivalent": "NIIRS",
            },
        )
