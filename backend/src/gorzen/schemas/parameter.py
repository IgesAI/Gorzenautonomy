"""Layer 1: Universal typed-parameter schema with uncertainty, provenance, and UI metadata."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class DistributionType(str, Enum):
    NORMAL = "normal"
    UNIFORM = "uniform"
    BETA = "beta"
    LOGNORMAL = "lognormal"
    EMPIRICAL = "empirical"
    TRIANGULAR = "triangular"
    WEIBULL = "weibull"


class UncertaintySpec(BaseModel):
    """Probabilistic description of parameter uncertainty."""

    distribution: DistributionType
    params: dict[str, float] = Field(
        ..., description="Distribution parameters, e.g. {'mean': 1.0, 'std': 0.05}"
    )
    bounds: tuple[float, float] | None = None
    correlation_group_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class ProvenanceSource(str, Enum):
    MANUFACTURER = "manufacturer"
    SPEC_SHEET = "spec_sheet"
    FLEET_PRIOR = "fleet_prior"
    CALIBRATED_POSTERIOR = "calibrated_posterior"
    USER_OVERRIDE = "user_override"
    SIMULATION = "simulation"


class Provenance(BaseModel):
    """Traceability record for a parameter value."""

    source: ProvenanceSource
    document_id: str | None = None
    test_id: str | None = None
    log_id: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    notes: str | None = None


class ControlType(str, Enum):
    SLIDER = "slider"
    NUMBER_INPUT = "number_input"
    DROPDOWN = "dropdown"
    TOGGLE = "toggle"
    TEXT_INPUT = "text_input"
    TABLE = "table"
    CURVE_EDITOR = "curve_editor"


class UIHints(BaseModel):
    """Metadata for UI rendering of a parameter field."""

    control_type: ControlType = ControlType.NUMBER_INPUT
    group: str = "general"
    advanced: bool = False
    display_name: str | None = None
    tooltip: str | None = None
    step: float | None = None
    precision: int | None = None
    enum_labels: dict[str, str] | None = None


class ParameterConstraints(BaseModel):
    """Validation constraints for a parameter value."""

    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[Any] | None = None
    regex_pattern: str | None = None
    cross_field_rules: list[str] = Field(
        default_factory=list,
        description="JSONPath-like references to related constraints",
    )


class TypedParameter(BaseModel, Generic[T]):
    """Universal parameter container with full metadata."""

    model_config = {"protected_namespaces": ()}

    value: Any  # Generic[T] constrained at runtime
    units: str = Field(..., description="UCUM-compatible unit string")
    default_value: Any | None = None
    default_source: Provenance | None = None
    uncertainty: UncertaintySpec | None = None
    constraints: ParameterConstraints | None = None
    provenance: Provenance | None = None
    ui_hints: UIHints | None = None
    model_binding: str | None = Field(
        None, description="Dot-path to the physics model coefficient, e.g. 'rotor.kT'"
    )


# ---------------------------------------------------------------------------
# Convenience factories
# ---------------------------------------------------------------------------

def param(
    value: Any,
    units: str,
    *,
    source: ProvenanceSource = ProvenanceSource.MANUFACTURER,
    uncertainty: UncertaintySpec | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    binding: str | None = None,
    advanced: bool = False,
    group: str = "general",
    display_name: str | None = None,
) -> TypedParameter:
    """Shortcut for building a TypedParameter with common defaults."""
    constraints = None
    if min_value is not None or max_value is not None:
        constraints = ParameterConstraints(min_value=min_value, max_value=max_value)
    return TypedParameter(
        value=value,
        units=units,
        default_value=value,
        default_source=Provenance(source=source),
        uncertainty=uncertainty,
        constraints=constraints,
        model_binding=binding,
        ui_hints=UIHints(
            advanced=advanced,
            group=group,
            display_name=display_name,
        ),
    )


class EnvelopeOutput(BaseModel):
    """A single output value with confidence bounds — never just a point estimate."""

    mean: float
    std: float
    percentiles: dict[str, float] = Field(
        default_factory=dict,
        description="Keyed by percentile label, e.g. {'p5': 12.3, 'p50': 15.0, 'p95': 17.8}",
    )
    units: str = ""
    top_contributors: list[str] = Field(
        default_factory=list,
        description="Parameters that dominate this output's uncertainty",
    )


class SensitivityEntry(BaseModel):
    parameter_name: str
    sobol_first_order: float | None = None
    sobol_total: float | None = None
    contribution_pct: float = 0.0


class EnvelopeResult(BaseModel):
    """Full envelope computation result returned by the engine."""

    outputs: dict[str, EnvelopeOutput]
    sensitivity: list[SensitivityEntry] = Field(default_factory=list)
    feasible: bool = True
    mission_completion_probability: float | None = None
    computation_time_s: float = 0.0
    method: str = "monte_carlo"
