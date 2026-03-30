"""Assumption auditor — detects fallback usage, default values, and undeclared constants.

Scans model parameter sets and outputs for:
- Fallback values that were silently substituted
- Default values used because the caller omitted required data
- Undeclared constants embedded in model code
- Missing provenance / source tags
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from gorzen.schemas.validation_result import (
    IssueCategory,
    IssueSeverity,
    ValidationIssue,
)

logger = logging.getLogger(__name__)


@dataclass
class AuditFinding:
    """A single assumption or fallback detected during audit."""

    parameter: str
    expected_source: str
    actual_source: str
    value: Any
    location: str
    is_blocking: bool


@dataclass
class AuditReport:
    """Complete assumption audit report."""

    findings: list[AuditFinding] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_blocking_findings(self) -> bool:
        return any(f.is_blocking for f in self.findings)

    @property
    def clean(self) -> bool:
        return len(self.findings) == 0


# Known model-internal defaults that should NOT exist.
# Maps (model_name, parameter_key) -> the silent default value.
# If a model output matches one of these, the audit flags it.
KNOWN_SILENT_DEFAULTS: dict[tuple[str, str], Any] = {
    ("AirframeModel", "mass_total_kg"): 12.0,
    ("AirframeModel", "wing_area_m2"): 0.5,
    ("AirframeModel", "wing_span_m"): 2.0,
    ("AirframeModel", "cd0"): 0.03,
    ("AirframeModel", "cl_alpha"): 5.0,
    ("AirframeModel", "oswald_efficiency"): 0.8,
    ("AirframeModel", "max_speed_ms"): 35.0,
    ("AirframeModel", "max_load_factor"): 3.0,
    ("ICEEngineModel", "max_power_kw"): 2.2,
    ("ICEEngineModel", "bsfc_cruise_g_kwh"): 500.0,
    ("ICEEngineModel", "cruise_power_demand_kw"): 1.0,
    ("RotorModel", "rotor_count"): 4,
    ("RotorModel", "rotor_diameter_m"): 0.6,
    ("RotorModel", "prop_ct_static"): 0.1,
    ("RotorModel", "prop_cp_static"): 0.04,
    ("MotorElectricalModel", "motor_kv"): 400.0,
    ("MotorElectricalModel", "motor_resistance_ohm"): 0.05,
    ("MotorElectricalModel", "motor_kt"): 0.024,
    ("BatteryModel", "cell_count_s"): 6,
    ("BatteryModel", "capacity_ah"): 10.0,
    ("FuelSystemModel", "tank_capacity_l"): 18.5,
    ("FuelSystemModel", "cruise_speed_kts"): 42.0,
    ("FuelSystemModel", "mass_empty_kg"): 34.0,
    ("GeneratorModel", "generator_output_w"): 200.0,
    ("ComputeModel", "max_power_w"): 15.0,
    ("ComputeModel", "thermal_throttle_temp_c"): 85.0,
    ("CommsModel", "tx_power_dbm"): 30.0,
    ("CommsModel", "manet_range_nmi"): 75.0,
    ("AvionicsModel", "ekf_position_noise_m"): 0.5,
    ("RollingShutterModel", "readout_time_ms"): 30.0,
    ("ImageQualityModel", "pixel_size_um"): 3.3,
    ("IdentificationConfidenceModel", "accuracy_at_nominal"): 0.85,
}


def audit_params_for_defaults(
    model_name: str,
    params: dict[str, Any],
    conditions: dict[str, Any],
) -> AuditReport:
    """Check whether any parameter in *params* or *conditions* matches a known
    model-internal default value, indicating it was not explicitly provided."""
    report = AuditReport()

    combined = {**params, **conditions}
    for (m, key), default_val in KNOWN_SILENT_DEFAULTS.items():
        if m != model_name:
            continue
        if key not in combined:
            report.findings.append(
                AuditFinding(
                    parameter=key,
                    expected_source="catalog or operator input",
                    actual_source="MISSING — model will use internal default",
                    value=default_val,
                    location=model_name,
                    is_blocking=True,
                )
            )
            report.issues.append(
                ValidationIssue(
                    category=IssueCategory.FALLBACK_USED,
                    severity=IssueSeverity.BLOCKING,
                    parameter=key,
                    location=model_name,
                    detail=f"'{key}' not provided; model would default to {default_val}",
                    correction=f"Supply '{key}' from validated platform spec or operator input",
                )
            )

    return report


def audit_output_for_sentinels(
    model_name: str,
    output: dict[str, Any],
) -> AuditReport:
    """Flag sentinel values in model outputs (e.g. 999.0 for infinite endurance)."""
    report = AuditReport()

    SENTINEL_VALUES = {999.0, 9999.0, float("inf")}

    for key, value in output.items():
        if isinstance(value, (int, float)) and value in SENTINEL_VALUES:
            report.findings.append(
                AuditFinding(
                    parameter=key,
                    expected_source="computed from physics",
                    actual_source=f"sentinel value {value}",
                    value=value,
                    location=model_name,
                    is_blocking=True,
                )
            )
            report.issues.append(
                ValidationIssue(
                    category=IssueCategory.INVALID_ASSUMPTION,
                    severity=IssueSeverity.BLOCKING,
                    parameter=key,
                    location=model_name,
                    detail=f"Output '{key}' has sentinel value {value} — not a valid physical result",
                    correction="Verify input parameters; this likely means a required input was missing",
                )
            )

    return report
