"""Strict parameter validation — rejects missing or estimated data.

Every computation that influences mission feasibility must pass through
this validator before execution.  If a required parameter is absent the
validator returns INSUFFICIENT_DATA rather than silently substituting a
default value.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Provenance(str, Enum):
    DATASHEET = "datasheet"
    ESTIMATED = "estimated"
    DERIVED = "derived"
    USER_INPUT = "user_input"
    UNKNOWN = "unknown"


class ViolationType(str, Enum):
    MISSING_DATA = "missing_data"
    ESTIMATED_PARAM = "estimated_param"
    FALLBACK_USED = "fallback_used"
    INVALID_CONSTANT = "invalid_constant"
    ASSUMPTION = "assumption"


@dataclass
class Violation:
    """A single rigour violation in the computation pipeline."""

    violation_type: ViolationType
    parameter: str
    location: str
    impact: str
    correction: str


@dataclass
class ParameterValidationResult:
    """Result of strict parameter validation."""

    valid: bool
    missing: list[str] = field(default_factory=list)
    estimated: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    confidence: str = "HIGH"

    @property
    def error_message(self) -> str | None:
        if not self.valid:
            parts: list[str] = []
            if self.missing:
                parts.append(f"INSUFFICIENT_DATA: Missing required parameters {self.missing}")
            if self.estimated:
                parts.append(
                    f"WARNING: Parameters from estimated sources (not datasheets): {self.estimated}"
                )
            return "; ".join(parts)
        return None


REQUIRED_SENSOR_PARAMS = [
    "sensor_width_mm",
    "sensor_height_mm",
    "focal_length_mm",
    "pixel_width",
    "pixel_height",
]

REQUIRED_PLATFORM_PARAMS = [
    "max_speed_ms",
    "cruise_speed_ms",
    "endurance_min",
    "payload_max_kg",
    "mtow_kg",
]

REQUIRED_MISSION_PARAMS = [
    "altitude_m",
    "airspeed_ms",
]

REQUIRED_BLUR_PARAMS = [
    "exposure_time_s",
    "max_blur_px",
]

REQUIRED_DETECTION_PARAMS = [
    "target_size_m",
    "min_pixels_on_target",
]

ESTIMATED_PARAMETERS: dict[str, str] = {
    "fuel_capacity_l": "Not in VA-series datasheets",
    "fuel_consumption_l_per_hr": "Not in VA-series datasheets",
}


def _is_present(params: dict[str, Any], key: str) -> bool:
    """Check whether a parameter is present and not None/NaN."""
    val = params.get(key)
    if val is None:
        return False
    if isinstance(val, float) and (val != val):  # NaN check
        return False
    return True


def validate_params(
    params: dict[str, Any],
    required: list[str],
    *,
    context: str = "",
) -> ParameterValidationResult:
    """Validate that all *required* keys exist in *params*.

    Returns a ParameterValidationResult.  When ``valid`` is ``False``
    the caller MUST NOT proceed with the computation — return
    INSUFFICIENT_DATA to the user instead.
    """
    missing = [p for p in required if not _is_present(params, p)]
    estimated = [p for p in required if _is_present(params, p) and p in ESTIMATED_PARAMETERS]

    violations: list[Violation] = []
    for p in missing:
        violations.append(
            Violation(
                violation_type=ViolationType.MISSING_DATA,
                parameter=p,
                location=context or "parameter_validation",
                impact=f"Cannot compute: {p} is required but not provided",
                correction=f"Supply {p} from platform datasheet or explicit mission input",
            )
        )
    for p in estimated:
        violations.append(
            Violation(
                violation_type=ViolationType.ESTIMATED_PARAM,
                parameter=p,
                location=context or "parameter_validation",
                impact=f"{p} is estimated ({ESTIMATED_PARAMETERS[p]}), not from a verified source",
                correction=f"Obtain {p} from manufacturer datasheet or ground-truth measurement",
            )
        )

    valid = len(missing) == 0

    if not valid:
        confidence = "INSUFFICIENT_DATA"
    elif estimated:
        confidence = "LOW"
    else:
        confidence = "HIGH"

    if missing:
        logger.warning(
            "parameter_validation: INSUFFICIENT_DATA context=%s missing=%s",
            context,
            missing,
        )

    return ParameterValidationResult(
        valid=valid,
        missing=missing,
        estimated=estimated,
        violations=violations,
        confidence=confidence,
    )


def validate_sensor_params(params: dict[str, Any]) -> ParameterValidationResult:
    return validate_params(params, REQUIRED_SENSOR_PARAMS, context="sensor")


def validate_platform_params(params: dict[str, Any]) -> ParameterValidationResult:
    return validate_params(params, REQUIRED_PLATFORM_PARAMS, context="platform")


def validate_mission_conditions(conditions: dict[str, Any]) -> ParameterValidationResult:
    return validate_params(conditions, REQUIRED_MISSION_PARAMS, context="mission_conditions")


def validate_blur_params(params: dict[str, Any]) -> ParameterValidationResult:
    return validate_params(params, REQUIRED_BLUR_PARAMS, context="motion_blur")


def validate_detection_params(conditions: dict[str, Any]) -> ParameterValidationResult:
    return validate_params(conditions, REQUIRED_DETECTION_PARAMS, context="detection")


def require_param(params: dict[str, Any], key: str, context: str = "") -> Any:
    """Extract a single required parameter or raise ``ValueError``.

    Returns float for numeric values, raw value for strings/bools.
    Use in hot paths where raising is acceptable (e.g. model evaluate).
    """
    if not _is_present(params, key):
        raise ValueError(
            f"INSUFFICIENT_DATA: '{key}' is required but missing"
            + (f" (context: {context})" if context else "")
        )
    val = params[key]
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return val
    return float(val)
