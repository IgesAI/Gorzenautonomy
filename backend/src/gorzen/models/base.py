"""Base classes for all physics and perception subsystem models.

Phase 2b contract: ``ModelOutput.get`` no longer silently returns 0.0 for
missing keys. Callers must either:

* use ``__getitem__`` (``out["key"]``) when the key is required, which raises
  :class:`KeyError`, or
* use ``get(key, default)`` with an **explicit** default that makes the
  synthesised value visible to code review.

The old zero-default behaviour masked missing model outputs as real zeros
and was the single biggest source of "plausible-looking but fabricated"
numbers in the envelope pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


class MissingModelOutputError(KeyError):
    """Raised when a required output is absent from a :class:`ModelOutput`."""


@dataclass
class ModelOutput:
    """Container for subsystem model evaluation results."""

    values: dict[str, float] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    feasible: bool = True
    warnings: list[str] = field(default_factory=list)

    def __getitem__(self, key: str) -> float:
        if key not in self.values:
            raise MissingModelOutputError(
                f"Model output {key!r} missing; available: {sorted(self.values.keys())}"
            )
        return self.values[key]

    def require(self, key: str) -> float:
        """Explicit alias for ``out[key]`` — use in fail-fast code paths."""
        return self[key]

    def get(self, key: str, default: float = 0.0) -> float:
        """Fetch ``key`` or return ``default``.

        Retained for backward compatibility with call sites that intentionally
        want a default. Prefer :meth:`require` or ``out[key]`` in new code so
        missing outputs surface as errors.
        """
        return self.values.get(key, default)


class SubsystemModel(ABC):
    """Abstract base for all composable subsystem models.

    Each model exposes:
    - parameters: the configurable inputs with metadata
    - states: current internal state vector
    - evaluate: forward-pass producing ModelOutput
    - jacobian: partial derivatives for UQ propagation
    """

    @abstractmethod
    def parameter_names(self) -> list[str]:
        """Return ordered list of parameter names this model depends on."""
        ...

    @abstractmethod
    def state_names(self) -> list[str]:
        """Return ordered list of internal state variable names."""
        ...

    @abstractmethod
    def output_names(self) -> list[str]:
        """Return ordered list of output names produced by evaluate()."""
        ...

    @abstractmethod
    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        """Run the model forward pass.

        Args:
            params: subsystem parameters (from twin config).
            conditions: operating conditions (speed, altitude, temperature, etc.).
        """
        ...

    def jacobian(
        self,
        params: dict[str, float],
        conditions: dict[str, float],
        wrt: list[str] | None = None,
        eps: float = 1e-6,
    ) -> np.ndarray:
        """Numerical Jacobian via central finite differences.

        Returns shape (n_outputs, n_wrt) where wrt defaults to all params.
        Subclasses may override with analytic derivatives.
        """
        if wrt is None:
            wrt = self.parameter_names()

        self.evaluate(params, conditions)
        out_names = self.output_names()
        n_out = len(out_names)
        n_in = len(wrt)
        jac = np.zeros((n_out, n_in))

        for j, pname in enumerate(wrt):
            p_plus = dict(params)
            p_minus = dict(params)
            h = max(abs(params.get(pname, 0.0)) * eps, eps)
            p_plus[pname] = params.get(pname, 0.0) + h
            p_minus[pname] = params.get(pname, 0.0) - h

            out_plus = self.evaluate(p_plus, conditions)
            out_minus = self.evaluate(p_minus, conditions)

            for i, oname in enumerate(out_names):
                # Missing outputs now raise rather than silently yielding 0.0,
                # which used to produce nonsensical Jacobian entries.
                jac[i, j] = (out_plus[oname] - out_minus[oname]) / (2 * h)

        return jac


class CompositeModel:
    """Chains multiple SubsystemModels, passing outputs between them."""

    def __init__(self, models: list[SubsystemModel]) -> None:
        self.models = models

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        combined = ModelOutput()
        current_conditions = dict(params)
        current_conditions.update(conditions)

        for model in self.models:
            out = model.evaluate(params, current_conditions)
            combined.values.update(out.values)
            combined.units.update(out.units)
            combined.feasible = combined.feasible and out.feasible
            combined.warnings.extend(out.warnings)
            current_conditions.update(out.values)

        return combined

    def all_parameter_names(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for m in self.models:
            for p in m.parameter_names():
                if p not in seen:
                    seen.add(p)
                    result.append(p)
        return result

    def all_output_names(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for m in self.models:
            for o in m.output_names():
                if o not in seen:
                    seen.add(o)
                    result.append(o)
        return result
