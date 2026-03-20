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

    # GIQE 5 coefficients — single unified equation (no RER bifurcation)
    # Reference: Griffith, "Updated GIQE", ASPRS/JACIE 2012-2014; NGA publications
    # NIIRS = c0 + c1*ln(GSD) + c2*ln(RER) + c3*(G/SNR) + c4*H
    # Uses natural log (ln) per GIQE 5 formulation
    GIQE_C0 = 9.57
    GIQE_C1 = -3.32    # GSD term (inches, natural log)
    GIQE_C2 = 3.32     # RER term (unified, no bifurcation)
    GIQE_C3 = -1.9     # noise gain / SNR term (G/SNR)
    GIQE_C4 = -2.0     # edge overshoot H (refined for sharpening artifacts)

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

        # GIQE 5: NIIRS = c0 + c1*ln(GSD_in) + c2*ln(RER) + c3*(G/SNR) + c4*H
        # GSD must be in inches; uses natural log (ln); G=1 (no noise gain), H=0 (no sharpening)
        gsd_inches = (gsd_cm / 2.54)  # cm -> inches
        niirs = (
            self.GIQE_C0
            + self.GIQE_C1 * np.log(gsd_inches + 1e-9)
            + self.GIQE_C2 * np.log(rer + 1e-9)
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
