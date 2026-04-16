"""Exceptions raised by the solver layer under strict / fail-fast mode."""

from __future__ import annotations


class SolverError(RuntimeError):
    """Base class for solver contract violations."""


class MissingSolverParamError(SolverError, KeyError):
    """A parameter required by the solver is not present in the twin/config."""

    def __init__(self, param: str, context: str = "") -> None:
        self.param = param
        self.context = context
        msg = f"Missing solver parameter {param!r}"
        if context:
            msg += f" ({context})"
        super().__init__(msg)


class TrimSolverError(SolverError, RuntimeError):
    """The trim / AoA solver did not converge for a given flight condition."""


class TrajectoryNotSolvedError(SolverError, RuntimeError):
    """The NLP trajectory solver returned infeasible / error status."""
