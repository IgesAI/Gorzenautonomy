"""Communications model: link budget, QoS, bandwidth-driven compression."""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel


class CommsModel(SubsystemModel):
    """RF link budget and bandwidth-constrained video quality model."""

    def parameter_names(self) -> list[str]:
        return [
            "tx_power_dbm", "antenna_gain_dbi", "receiver_sensitivity_dbm",
            "max_range_km", "bandwidth_mbps", "required_latency_ms",
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
        tx_power = params.get("tx_power_dbm", 20.0)
        ant_gain = params.get("antenna_gain_dbi", 2.0)
        rx_sens = params.get("receiver_sensitivity_dbm", -100.0)
        max_range = params.get("max_range_km", 5.0)
        bw = params.get("bandwidth_mbps", 2.0)
        req_latency = params.get("required_latency_ms", 200.0)

        distance_km = conditions.get("distance_to_gcs_km", 1.0)
        encoding_bitrate = conditions.get("encoding_bitrate_mbps", 20.0)

        # Free-space path loss at 900 MHz
        freq_mhz = 900.0
        fspl = 20 * np.log10(distance_km + 1e-6) + 20 * np.log10(freq_mhz) + 32.44

        received_power = tx_power + 2 * ant_gain - fspl
        link_margin = received_power - rx_sens

        effective_range = max_range if link_margin > 6.0 else max_range * (link_margin / 6.0)

        # Bandwidth constraint on video quality
        if encoding_bitrate <= bw:
            achievable_bitrate = encoding_bitrate
            quality_factor = 90.0
        else:
            achievable_bitrate = bw
            quality_factor = max(10.0, 90.0 * (bw / encoding_bitrate))

        comms_latency = 20.0 + (distance_km / 300.0) * 1e3 * 0.001  # propagation negligible; processing dominant
        link_feasible = link_margin > 3.0 and comms_latency < req_latency

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
