"""Hierarchical optimizer: discrete outer + continuous inner + risk layer.

Outer loop: enumerate discrete choices (component variants, camera, AI model).
Inner loop: continuous optimization (speed, altitude, photo cadence, overlap).
Risk layer: chance constraints ensuring P(success) >= threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Any, Callable

import numpy as np

from gorzen.schemas.parameter import UncertaintySpec
from gorzen.uq.propagation import UQInput, UQPropagator


@dataclass
class DiscreteChoice:
    """A discrete configuration choice for the outer loop."""

    name: str
    options: list[Any]
    labels: list[str] | None = None


@dataclass
class ContinuousVariable:
    """A continuous optimization variable for the inner loop."""

    name: str
    lower: float
    upper: float
    initial: float | None = None


@dataclass
class RiskConstraint:
    """Probabilistic constraint: P(output >= threshold) >= confidence."""

    output_name: str
    threshold: float
    direction: str = ">="
    required_confidence: float = 0.95


@dataclass
class OptimizationResult:
    """Result of hierarchical optimization."""

    best_discrete: dict[str, Any] = field(default_factory=dict)
    best_continuous: dict[str, float] = field(default_factory=dict)
    objective_value: float = float("inf")
    mission_completion_probability: float = 0.0
    all_candidates: list[dict] = field(default_factory=list)
    feasible: bool = False


class HierarchicalOptimizer:
    """Two-level optimizer with risk-aware constraint checking."""

    def __init__(
        self,
        mc_samples: int = 500,
        inner_grid_resolution: int = 10,
    ):
        self.mc_samples = mc_samples
        self.inner_resolution = inner_grid_resolution

    def optimize(
        self,
        model_fn: Callable[[dict[str, Any]], dict[str, float]],
        discrete_choices: list[DiscreteChoice],
        continuous_vars: list[ContinuousVariable],
        objective_name: str,
        maximize: bool = True,
        risk_constraints: list[RiskConstraint] | None = None,
        uq_inputs: list[UQInput] | None = None,
    ) -> OptimizationResult:
        """Run hierarchical optimization.

        Outer loop exhaustively enumerates discrete choices.
        Inner loop uses grid search over continuous variables.
        Risk layer evaluates chance constraints via UQ.
        """
        if not discrete_choices:
            discrete_combos = [{}]
        else:
            keys = [dc.name for dc in discrete_choices]
            vals = [dc.options for dc in discrete_choices]
            discrete_combos = [dict(zip(keys, combo)) for combo in product(*vals)]

        best = OptimizationResult()
        best.objective_value = float("-inf") if maximize else float("inf")

        for dc in discrete_combos:
            inner_result = self._inner_loop(
                model_fn, dc, continuous_vars, objective_name, maximize,
                risk_constraints, uq_inputs,
            )
            if inner_result is None:
                continue

            obj, cvars, mcp = inner_result
            improved = (obj > best.objective_value) if maximize else (obj < best.objective_value)

            candidate = {
                "discrete": dict(dc),
                "continuous": dict(cvars),
                "objective": obj,
                "mcp": mcp,
            }
            best.all_candidates.append(candidate)

            if improved:
                best.best_discrete = dict(dc)
                best.best_continuous = dict(cvars)
                best.objective_value = obj
                best.mission_completion_probability = mcp
                best.feasible = True

        return best

    def _inner_loop(
        self,
        model_fn: Callable,
        discrete_config: dict[str, Any],
        continuous_vars: list[ContinuousVariable],
        objective_name: str,
        maximize: bool,
        risk_constraints: list[RiskConstraint] | None,
        uq_inputs: list[UQInput] | None,
    ) -> tuple[float, dict[str, float], float] | None:
        """Grid-search inner loop over continuous variables."""
        if not continuous_vars:
            merged = dict(discrete_config)
            try:
                out = model_fn(merged)
            except Exception:
                return None
            return out.get(objective_name, 0.0), {}, 1.0

        # Build grid
        grids = [
            np.linspace(cv.lower, cv.upper, self.inner_resolution)
            for cv in continuous_vars
        ]
        grid_points = list(product(*grids))

        best_obj = float("-inf") if maximize else float("inf")
        best_cvars: dict[str, float] = {}
        best_mcp = 0.0

        for point in grid_points:
            cvars = {cv.name: float(point[i]) for i, cv in enumerate(continuous_vars)}
            merged = dict(discrete_config)
            merged.update(cvars)

            try:
                out = model_fn(merged)
            except Exception:
                continue

            obj = out.get(objective_name, 0.0)

            # Risk constraint checking
            mcp = 1.0
            if risk_constraints and uq_inputs:
                constraints = {
                    rc.output_name: (rc.threshold, rc.direction)
                    for rc in risk_constraints
                }

                def uq_model(inp: dict[str, float]) -> dict[str, float]:
                    m = dict(merged)
                    m.update(inp)
                    return model_fn(m)

                propagator = UQPropagator(method="monte_carlo", mc_samples=self.mc_samples)
                uq_result = propagator.propagate(uq_model, uq_inputs, constraints=constraints)
                mcp = uq_result.mission_completion_probability or 0.0

                # Check all constraints meet required confidence
                if any(mcp < rc.required_confidence for rc in risk_constraints):
                    continue

            improved = (obj > best_obj) if maximize else (obj < best_obj)
            if improved:
                best_obj = obj
                best_cvars = cvars
                best_mcp = mcp

        if not best_cvars and not continuous_vars:
            return None
        return best_obj, best_cvars, best_mcp
