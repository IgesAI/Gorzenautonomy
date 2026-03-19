"""Unified UQ propagation interface dispatching to MC, UT, or PCE."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from gorzen.schemas.parameter import EnvelopeOutput, SensitivityEntry, UncertaintySpec
from gorzen.uq.monte_carlo import MCInput, MCResult, MonteCarloEngine
from gorzen.uq.pce import PCEResult, PCESurrogate
from gorzen.uq.unscented import UTResult, UnscentedTransform


@dataclass
class UQInput:
    """Unified uncertain input specification."""

    name: str
    nominal: float
    uncertainty: UncertaintySpec | None = None
    bounds: tuple[float, float] | None = None
    discrete_choices: list[float] | None = None
    discrete_weights: list[float] | None = None


@dataclass
class UQResult:
    """Unified output from any UQ propagation method."""

    method: str
    outputs: dict[str, EnvelopeOutput] = field(default_factory=dict)
    sensitivity: list[SensitivityEntry] = field(default_factory=list)
    mission_completion_probability: float | None = None
    raw_mc: MCResult | None = None
    raw_ut: UTResult | None = None
    raw_pce: PCEResult | None = None


class UQPropagator:
    """Unified interface for uncertainty propagation.

    Dispatches to Monte Carlo, Unscented Transform, or PCE based on method choice.
    """

    def __init__(
        self,
        method: str = "monte_carlo",
        mc_samples: int = 1000,
        pce_order: int = 3,
        seed: int | None = None,
    ):
        self.method = method
        self.mc_samples = mc_samples
        self.pce_order = pce_order
        self.seed = seed

    def propagate(
        self,
        model_fn: Callable[[dict[str, float]], dict[str, float]],
        inputs: list[UQInput],
        output_names: list[str] | None = None,
        constraints: dict[str, tuple[float, str]] | None = None,
    ) -> UQResult:
        """Run uncertainty propagation through the model.

        Args:
            model_fn: Maps parameter dict to output dict.
            inputs: Uncertain input specifications.
            output_names: Which outputs to report (None = all).
            constraints: {output_name: (threshold, direction)} for P(constraint).
        """
        if self.method == "monte_carlo":
            return self._run_mc(model_fn, inputs, output_names, constraints)
        elif self.method == "unscented":
            return self._run_ut(model_fn, inputs, output_names)
        elif self.method == "pce":
            return self._run_pce(model_fn, inputs, output_names)
        else:
            return self._run_mc(model_fn, inputs, output_names, constraints)

    def _run_mc(
        self,
        model_fn: Callable,
        inputs: list[UQInput],
        output_names: list[str] | None,
        constraints: dict[str, tuple[float, str]] | None,
    ) -> UQResult:
        mc_inputs = [
            MCInput(
                name=inp.name,
                nominal=inp.nominal,
                uncertainty=inp.uncertainty,
                discrete_choices=inp.discrete_choices,
                discrete_weights=inp.discrete_weights,
            )
            for inp in inputs
        ]

        engine = MonteCarloEngine(n_samples=self.mc_samples, seed=self.seed)
        mc_result = engine.propagate(model_fn, mc_inputs)

        result = UQResult(method="monte_carlo", raw_mc=mc_result)

        names = output_names or list(mc_result.output_samples.keys())
        for name in names:
            if name in mc_result.output_samples:
                result.outputs[name] = mc_result.envelope_output(name)

        if names:
            if constraints:
                constraint_names = list(constraints.keys())
                result.sensitivity = mc_result.sensitivity_ranking_mcp(constraint_names)
            else:
                result.sensitivity = mc_result.sensitivity_ranking(names[0])

        # Mission completion probability: all constraints satisfied simultaneously
        if constraints:
            all_satisfied = np.ones(mc_result.n_samples, dtype=bool)
            for oname, (thresh, direction) in constraints.items():
                if oname in mc_result.output_samples:
                    s = mc_result.output_samples[oname]
                    if direction == ">=":
                        all_satisfied &= s >= thresh
                    elif direction == "<=":
                        all_satisfied &= s <= thresh
            result.mission_completion_probability = float(np.mean(all_satisfied))

        return result

    def _run_ut(
        self,
        model_fn: Callable,
        inputs: list[UQInput],
        output_names: list[str] | None,
    ) -> UQResult:
        continuous = [inp for inp in inputs if inp.uncertainty is not None and inp.discrete_choices is None]

        param_names = [inp.name for inp in continuous]
        means = np.array([inp.nominal for inp in continuous])

        # Build diagonal covariance from uncertainty specs
        variances = []
        for inp in continuous:
            if inp.uncertainty:
                std = inp.uncertainty.params.get("std", abs(inp.nominal) * 0.05)
                variances.append(std ** 2)
            else:
                variances.append((abs(inp.nominal) * 0.01) ** 2)
        cov = np.diag(variances)

        ut = UnscentedTransform()
        ut_result = ut.propagate(model_fn, param_names, means, cov)

        result = UQResult(method="unscented", raw_ut=ut_result)
        names = output_names or list(ut_result.output_mean.keys())
        for name in names:
            if name in ut_result.output_mean:
                result.outputs[name] = ut_result.envelope_output(name)

        return result

    def _run_pce(
        self,
        model_fn: Callable,
        inputs: list[UQInput],
        output_names: list[str] | None,
    ) -> UQResult:
        continuous = [inp for inp in inputs if inp.uncertainty is not None and inp.discrete_choices is None]

        param_names = [inp.name for inp in continuous]
        bounds = []
        for inp in continuous:
            if inp.bounds:
                bounds.append(inp.bounds)
            elif inp.uncertainty and inp.uncertainty.bounds:
                bounds.append(inp.uncertainty.bounds)
            else:
                std = inp.uncertainty.params.get("std", abs(inp.nominal) * 0.1) if inp.uncertainty else abs(inp.nominal) * 0.1
                bounds.append((inp.nominal - 3 * std, inp.nominal + 3 * std))

        pce = PCESurrogate(max_order=self.pce_order)
        pce.fit(model_fn, param_names, bounds)
        pce_result = pce.compute_statistics()

        result = UQResult(method="pce", raw_pce=pce_result)
        names = output_names or list(pce_result.output_mean.keys())
        for name in names:
            if name in pce_result.output_mean:
                result.outputs[name] = pce_result.envelope_output(name)

        if names:
            result.sensitivity = pce_result.sensitivity_entries(names[0])

        return result
