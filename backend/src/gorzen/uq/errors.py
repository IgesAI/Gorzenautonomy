"""Exception types for UQ fail-fast semantics.

Phase 2 of the backend audit removes every silent ``get(name, 0.0)`` and
``except Exception: pass`` from the UQ stack. These exceptions replace the
previous fabricated zeros so callers learn about missing outputs or malformed
inputs immediately, rather than reading plausible-looking numbers that were
really synthesized from defaults.
"""

from __future__ import annotations


class UQError(RuntimeError):
    """Base class for UQ contract violations."""


class MissingOutputError(UQError, KeyError):
    """A requested output name is not present in the UQ result."""

    def __init__(self, output_name: str, available: list[str] | None = None) -> None:
        self.output_name = output_name
        self.available = list(available or [])
        msg = f"Output {output_name!r} not present in UQ result"
        if self.available:
            msg += f" (available: {self.available})"
        super().__init__(msg)


class MissingUncertaintyError(UQError, ValueError):
    """An input was marked as uncertain but no std / bounds were supplied.

    Replaces the old silent ``inp.uncertainty.params.get('std', |nominal|*0.05)``
    path that fabricated a 5% coefficient of variation when the user forgot
    to declare one.
    """


class InvalidCorrelationError(UQError, ValueError):
    """The correlation matrix is not symmetric positive-definite."""


class ModelEvaluationError(UQError, RuntimeError):
    """A model evaluation failed during sampling under strict mode."""


class UnknownMethodError(UQError, ValueError):
    """An unsupported UQ method name was requested."""
