"""Provenance-aware parameter resolver.

Pulls values ONLY from approved sources:
1. Catalog entry (datasheet-backed component profile)
2. Operator mission input
3. Derived computation (with explicit derivation chain)

Every resolved parameter carries provenance.  Unresolved parameters
are denied — the resolver will NOT invent, estimate, or default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from gorzen.schemas.catalog import CatalogProvenance, ParameterClassification
from gorzen.schemas.validation_result import (
    IssueCategory,
    IssueSeverity,
    ParameterProvenanceRecord,
    ValidationIssue,
)

logger = logging.getLogger(__name__)


@dataclass
class ResolvedParameter:
    """A parameter value with full traceability."""

    name: str
    value: Any
    source: str
    classification: ParameterClassification
    source_file: str | None = None
    source_page: str | None = None


@dataclass
class ResolutionResult:
    """Outcome of resolving a set of required parameters."""

    resolved: dict[str, ResolvedParameter] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    provenance_records: list[ParameterProvenanceRecord] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.missing) == 0

    def get_flat(self) -> dict[str, Any]:
        """Return a flat dict of resolved parameter name→value."""
        return {name: rp.value for name, rp in self.resolved.items()}


class ParameterResolver:
    """Resolve required parameters from approved sources only.

    Usage::

        resolver = ParameterResolver()
        resolver.add_catalog_params(catalog_entry.parameters, catalog_entry.parameter_provenance)
        resolver.add_operator_inputs(mission_config_dict)
        result = resolver.resolve(REQUIRED_KEYS)

        if not result.valid:
            # INSUFFICIENT_DATA — do not proceed
            ...
    """

    def __init__(self) -> None:
        self._catalog: dict[str, tuple[Any, CatalogProvenance | None]] = {}
        self._operator: dict[str, Any] = {}
        self._derived: dict[str, tuple[Any, str]] = {}

    def add_catalog_params(
        self,
        params: dict[str, Any],
        provenance: dict[str, Any] | None = None,
    ) -> None:
        """Register parameters from a catalog entry (datasheet-backed)."""
        prov_map = provenance or {}
        for key, value in params.items():
            prov = prov_map.get(key)
            if isinstance(prov, dict):
                prov = CatalogProvenance(**prov)
            self._catalog[key] = (value, prov)

    def add_operator_inputs(self, inputs: dict[str, Any]) -> None:
        """Register explicit operator / mission inputs."""
        self._operator.update(inputs)

    def add_derived(self, key: str, value: Any, derivation: str) -> None:
        """Register a derived parameter with its derivation description."""
        self._derived[key] = (value, derivation)

    def resolve(self, required: list[str], *, context: str = "") -> ResolutionResult:
        """Attempt to resolve all *required* parameters.

        Priority: operator_input > catalog > derived.
        Anything not found → missing (INSUFFICIENT_DATA).
        """
        result = ResolutionResult()

        for key in required:
            if key in self._operator:
                rp = ResolvedParameter(
                    name=key,
                    value=self._operator[key],
                    source="operator_input",
                    classification=ParameterClassification.OPERATOR_INPUT_REQUIRED,
                )
                result.resolved[key] = rp
                result.provenance_records.append(
                    ParameterProvenanceRecord(
                        parameter_name=key,
                        value=rp.value,
                        source="operator_input",
                        classification=rp.classification.value,
                    )
                )

            elif key in self._catalog:
                value, prov = self._catalog[key]
                rp = ResolvedParameter(
                    name=key,
                    value=value,
                    source="catalog",
                    classification=ParameterClassification.DATASHEET_LOCKED,
                    source_file=prov.source_file if prov else None,
                    source_page=prov.source_page if prov else None,
                )
                result.resolved[key] = rp
                result.provenance_records.append(
                    ParameterProvenanceRecord(
                        parameter_name=key,
                        value=value,
                        source="catalog",
                        source_file=rp.source_file,
                        source_page=rp.source_page,
                        classification=rp.classification.value,
                    )
                )

            elif key in self._derived:
                value, derivation = self._derived[key]
                rp = ResolvedParameter(
                    name=key,
                    value=value,
                    source=f"derived: {derivation}",
                    classification=ParameterClassification.DERIVED_ONLY,
                )
                result.resolved[key] = rp
                result.provenance_records.append(
                    ParameterProvenanceRecord(
                        parameter_name=key,
                        value=value,
                        source=f"derived: {derivation}",
                        classification=rp.classification.value,
                    )
                )

            else:
                result.missing.append(key)
                result.issues.append(
                    ValidationIssue(
                        category=IssueCategory.MISSING_INPUT,
                        severity=IssueSeverity.BLOCKING,
                        parameter=key,
                        location=context or "parameter_resolver",
                        detail=f"Required parameter '{key}' not found in any approved source",
                        correction=f"Provide '{key}' via catalog entry, operator input, or explicit derivation",
                    )
                )

        if result.missing:
            logger.warning(
                "parameter_resolver: INSUFFICIENT_DATA context=%s missing=%s",
                context,
                result.missing,
            )

        return result
