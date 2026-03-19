"""Envelope computation request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from gorzen.schemas.parameter import EnvelopeOutput, EnvelopeResult, SensitivityEntry  # noqa: F401


class EnvelopeSurface(BaseModel):
    """A 2-D gridded surface (e.g., speed x altitude) with confidence bands."""

    x_label: str
    y_label: str
    z_label: str
    x_values: list[float]
    y_values: list[float]
    z_mean: list[list[float]]
    z_p5: list[list[float]]
    z_p95: list[list[float]]
    feasible_mask: list[list[bool]] | None = None


class EnvelopeRequest(BaseModel):
    """Request body for computing operating envelopes."""

    twin_id: str
    speed_range_ms: tuple[float, float] = (0.0, 35.0)
    altitude_range_m: tuple[float, float] = (10.0, 200.0)
    grid_resolution: int = 20
    uq_method: str = "monte_carlo"
    mc_samples: int = 500
    include_sensitivity: bool = True


class EnvelopeResponse(BaseModel):
    """Full envelope computation response."""

    speed_altitude_feasibility: EnvelopeSurface | None = None
    safe_inspection_speed: EnvelopeOutput | None = None
    fuel_endurance: EnvelopeOutput | None = None
    battery_reserve: EnvelopeOutput | None = None
    fuel_flow_rate: EnvelopeOutput | None = None
    identification_confidence: EnvelopeSurface | None = None
    endurance_surface: EnvelopeSurface | None = None
    mission_completion_probability: float | None = None
    sensitivity: list[SensitivityEntry] = Field(default_factory=list)
    computation_time_s: float = 0.0
    warnings: list[str] = Field(default_factory=list)
