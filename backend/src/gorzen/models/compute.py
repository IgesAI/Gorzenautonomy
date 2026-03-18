"""Compute model: SoC thermal throttling, inference latency."""

from __future__ import annotations

from gorzen.models.base import ModelOutput, SubsystemModel


class ComputeModel(SubsystemModel):
    """Onboard compute performance model with thermal throttling."""

    def parameter_names(self) -> list[str]:
        return [
            "max_power_w", "thermal_throttle_temp_c",
            "inference_latency_ms", "max_throughput_fps",
        ]

    def state_names(self) -> list[str]:
        return ["junction_temp_c"]

    def output_names(self) -> list[str]:
        return [
            "effective_throughput_fps", "effective_latency_ms",
            "compute_power_W", "throttle_factor",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        max_power = params.get("max_power_w", 15.0)
        throttle_temp = params.get("thermal_throttle_temp_c", 85.0)
        base_latency = params.get("inference_latency_ms", 30.0)
        max_fps = params.get("max_throughput_fps", 30.0)

        ambient_temp = conditions.get("temperature_at_alt_c", 25.0)

        # Simplified thermal model: junction temp rises with ambient + power dissipation
        thermal_resistance = 3.0  # degC/W approximate
        junction_temp = ambient_temp + max_power * thermal_resistance

        if junction_temp > throttle_temp:
            throttle_factor = max(0.3, 1.0 - (junction_temp - throttle_temp) / 30.0)
        else:
            throttle_factor = 1.0

        effective_fps = max_fps * throttle_factor
        effective_latency = base_latency / (throttle_factor + 1e-6)
        compute_power = max_power * throttle_factor

        return ModelOutput(
            values={
                "effective_throughput_fps": effective_fps,
                "effective_latency_ms": effective_latency,
                "compute_power_W": compute_power,
                "throttle_factor": throttle_factor,
            },
            units={
                "effective_throughput_fps": "Hz",
                "effective_latency_ms": "ms",
                "compute_power_W": "W",
                "throttle_factor": "1",
            },
        )
