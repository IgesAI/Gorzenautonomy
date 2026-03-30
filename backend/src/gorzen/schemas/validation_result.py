"""Strict validation result contract for pre-flight mission validation.

Every solve / computation must produce a ValidationReport before proceeding.
If the report contains blocking issues, the solve MUST NOT continue.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MissionStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class IssueSeverity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


class IssueCategory(str, Enum):
    MISSING_INPUT = "missing_input"
    FALLBACK_USED = "fallback_used"
    INVALID_ASSUMPTION = "invalid_assumption"
    ESTIMATED_PARAMETER = "estimated_parameter"
    UNVERIFIED_PROFILE = "unverified_profile"
    CONSTRAINT_VIOLATED = "constraint_violated"
    UNIT_MISMATCH = "unit_mismatch"


class ValidationIssue(BaseModel):
    """A single issue found during validation."""

    category: IssueCategory
    severity: IssueSeverity
    parameter: str
    location: str
    detail: str
    correction: str | None = None


class ParameterProvenanceRecord(BaseModel):
    """Traceability record for a resolved parameter value used in computation."""

    parameter_name: str
    value: Any
    source: str
    source_file: str | None = None
    source_page: str | None = None
    classification: str | None = None
    is_verified: bool = True


class ConstraintCheckResult(BaseModel):
    """Result of a single constraint check."""

    name: str
    passed: bool
    value: float
    limit: float
    unit: str
    detail: str


class DetectionValidation(BaseModel):
    """Pixels-on-target detection validation result."""

    required_pot: float
    achieved_pot: float
    margin_pct: float
    status: MissionStatus


class ConfidenceClass(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ValidatedConfiguration(BaseModel):
    """The validated platform/sensor/mission configuration."""

    platform_id: str | None = None
    platform_name: str | None = None
    sensor_name: str | None = None
    altitude_m: float | None = None
    velocity_ms: float | None = None
    flight_pattern: str | None = None
    exposure_time_s: float | None = None


class ValidationReport(BaseModel):
    """Complete pre-flight validation report.

    This is the authoritative output of the validation engine.
    If ``mission_status`` is not PASS, the mission MUST NOT proceed.
    """

    mission_status: MissionStatus
    validated_configuration: ValidatedConfiguration | None = None

    blocking_issues: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    info: list[ValidationIssue] = Field(default_factory=list)

    missing_inputs: list[str] = Field(default_factory=list)
    invalid_assumptions: list[str] = Field(default_factory=list)
    estimated_parameters: list[str] = Field(default_factory=list)

    parameter_provenance: list[ParameterProvenanceRecord] = Field(default_factory=list)

    detection: DetectionValidation | None = None

    constraint_checks: list[ConstraintCheckResult] = Field(default_factory=list)

    confidence: ConfidenceClass = ConfidenceClass.INSUFFICIENT_DATA
    confidence_reason: str = ""

    computation_time_s: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_blocking(self) -> bool:
        return self.mission_status != MissionStatus.PASS

    @property
    def all_issues(self) -> list[ValidationIssue]:
        return self.blocking_issues + self.warnings + self.info
