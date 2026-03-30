"""Computation audit trail — records the provenance of every derived value.

Every output produced by the mission planning pipeline must be traceable
back to its source parameters.  This module provides a lightweight
``AuditTrail`` that accumulates derivation steps so the final report
can answer "where did this number come from?" for every line item.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DerivationStep:
    """One step in a computation chain."""

    output_name: str
    formula: str
    inputs: dict[str, float]
    result: float
    units: str
    source: str


@dataclass
class AuditTrail:
    """Accumulator for full-traceability computation records."""

    steps: list[DerivationStep] = field(default_factory=list)

    def record(
        self,
        output_name: str,
        formula: str,
        inputs: dict[str, float],
        result: float,
        units: str = "",
        source: str = "",
    ) -> float:
        """Record a derivation step and return *result* for inline chaining."""
        self.steps.append(
            DerivationStep(
                output_name=output_name,
                formula=formula,
                inputs=inputs,
                result=result,
                units=units,
                source=source,
            )
        )
        return result

    def to_dict(self) -> list[dict[str, Any]]:
        return [
            {
                "output": s.output_name,
                "formula": s.formula,
                "inputs": s.inputs,
                "result": s.result,
                "units": s.units,
                "source": s.source,
            }
            for s in self.steps
        ]
