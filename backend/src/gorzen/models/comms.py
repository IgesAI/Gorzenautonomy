"""Communications model: link budget, QoS, bandwidth-driven compression."""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel
from gorzen.validation.parameter_validator import require_param


class CommsModel(SubsystemModel):
    """RF link budget and bandwidth-constrained video quality model.

    Supports MANET and SATCOM links with separate bandwidth/latency profiles.
    """

    def parameter_names(self) -> list[str]:
        return [
            "tx_power_dbm",
            "antenna_gain_dbi",
            "receiver_sensitivity_dbm",
            "manet_range_nmi",
            "manet_bandwidth_mbps",
            "satcom_available",
            "satcom_bandwidth_mbps",
        ]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return [
            "link_margin_db",
            "effective_range_km",
            "achievable_bitrate_mbps",
            "compression_quality_factor",
            "comms_latency_ms",
            "link_feasible",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        tx_power = require_param(params, "tx_power_dbm", "CommsModel")
        ant_gain = require_param(params, "antenna_gain_dbi", "CommsModel")
        rx_sens = require_param(params, "receiver_sensitivity_dbm", "CommsModel")
        manet_range_nmi = require_param(params, "manet_range_nmi", "CommsModel")
        manet_bw = require_param(params, "manet_bandwidth_mbps", "CommsModel")
        satcom = require_param(params, "satcom_available", "CommsModel")
        satcom_bw = require_param(params, "satcom_bandwidth_mbps", "CommsModel")

        distance_km = require_param(conditions, "distance_to_gcs_km", "CommsModel")
        encoding_bitrate = require_param(params, "encoding_bitrate_mbps", "CommsModel")

        # Link budget at MANET frequency (~1350 MHz)
        freq_mhz = require_param(conditions, "manet_frequency_mhz", "CommsModel")
        fspl = 20 * np.log10(max(distance_km, 0.01)) + 20 * np.log10(freq_mhz) + 32.45

        received_power = tx_power + 2 * ant_gain - fspl
        link_margin = received_power - rx_sens

        max_range_km = manet_range_nmi * 1.852
        # HEURISTIC: link margin policy
        effective_range = (
            max_range_km if link_margin > 6.0 else max(0, max_range_km * (link_margin / 6.0))
        )

        # Available bandwidth: use MANET bandwidth, fall back to SATCOM if out of MANET range
        if distance_km <= max_range_km:
            available_bw = manet_bw
        elif satcom > 0.5:
            available_bw = satcom_bw
        else:
            available_bw = 0.1

        # Compression quality: higher bandwidth = less compression needed
        if encoding_bitrate <= available_bw:
            achievable_bitrate = encoding_bitrate
            quality_factor = 90.0
        else:
            achievable_bitrate = available_bw
            quality_factor = max(20.0, 90.0 * (available_bw / encoding_bitrate))

        comms_latency = 20.0 if distance_km <= max_range_km else 600.0
        link_feasible = link_margin > 3.0  # HEURISTIC: link margin policy

        return ModelOutput(
            values={
                "link_margin_db": link_margin,
                "effective_range_km": effective_range,
                "achievable_bitrate_mbps": achievable_bitrate,
                "compression_quality_factor": quality_factor,
                "comms_latency_ms": comms_latency,
                "link_feasible": float(link_feasible),
            },
            units={
                "link_margin_db": "dB",
                "effective_range_km": "km",
                "achievable_bitrate_mbps": "Mbps",
                "compression_quality_factor": "1",
                "comms_latency_ms": "ms",
                "link_feasible": "1",
            },
            feasible=link_feasible,
        )
