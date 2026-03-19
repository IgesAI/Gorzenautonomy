"""Communications model: link budget, QoS, bandwidth-driven compression."""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel


class CommsModel(SubsystemModel):
    """RF link budget and bandwidth-constrained video quality model.

    Supports MANET and SATCOM links with separate bandwidth/latency profiles.
    """

    def parameter_names(self) -> list[str]:
        return [
            "tx_power_dbm", "antenna_gain_dbi", "receiver_sensitivity_dbm",
            "manet_range_nmi", "manet_bandwidth_mbps",
            "satcom_available", "satcom_bandwidth_mbps",
        ]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return [
            "link_margin_db", "effective_range_km",
            "achievable_bitrate_mbps", "compression_quality_factor",
            "comms_latency_ms", "link_feasible",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        tx_power = conditions.get("tx_power_dbm", params.get("tx_power_dbm", 30.0))
        ant_gain = conditions.get("antenna_gain_dbi", params.get("antenna_gain_dbi", 5.0))
        rx_sens = conditions.get("receiver_sensitivity_dbm", params.get("receiver_sensitivity_dbm", -100.0))
        manet_range_nmi = conditions.get("manet_range_nmi", params.get("manet_range_nmi", 75.0))
        manet_bw = conditions.get("manet_bandwidth_mbps", params.get("manet_bandwidth_mbps", 10.0))
        satcom = conditions.get("satcom_available", params.get("satcom_available", 1.0))
        satcom_bw = conditions.get("satcom_bandwidth_mbps", params.get("satcom_bandwidth_mbps", 2.0))

        distance_km = conditions.get("distance_to_gcs_km", 10.0)
        encoding_bitrate = conditions.get("encoding_bitrate_mbps", params.get("encoding_bitrate_mbps", 8.0))

        # Link budget at MANET frequency (~1350 MHz)
        freq_mhz = conditions.get("manet_frequency_mhz", 1350.0)
        fspl = 20 * np.log10(max(distance_km, 0.01)) + 20 * np.log10(freq_mhz) + 32.45

        received_power = tx_power + 2 * ant_gain - fspl
        link_margin = received_power - rx_sens

        max_range_km = manet_range_nmi * 1.852
        effective_range = max_range_km if link_margin > 6.0 else max(0, max_range_km * (link_margin / 6.0))

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
        link_feasible = link_margin > 3.0

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
                "link_margin_db": "dB", "effective_range_km": "km",
                "achievable_bitrate_mbps": "Mbps",
                "compression_quality_factor": "1",
                "comms_latency_ms": "ms", "link_feasible": "1",
            },
            feasible=link_feasible,
        )
