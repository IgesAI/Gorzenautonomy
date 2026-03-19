"""Monte Carlo sampling engine with mission completion probability.

Baseline truth engine: handles arbitrary nonlinearities, discrete choices,
and mixed distributions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from gorzen.schemas.parameter import EnvelopeOutput, SensitivityEntry, UncertaintySpec
from gorzen.uq.distributions import sample_correlated, sample_from_spec


@dataclass
class MCInput:
    """Defines an uncertain input for Monte Carlo sampling."""

    name: str
    nominal: float
    uncertainty: UncertaintySpec | None = None
    discrete_choices: list[float] | None = None
    discrete_weights: list[float] | None = None


@dataclass
class MCResult:
    """Results from a Monte Carlo uncertainty propagation run."""

    output_samples: dict[str, np.ndarray] = field(default_factory=dict)
    input_samples: dict[str, np.ndarray] = field(default_factory=dict)
    n_samples: int = 0

    def envelope_output(self, name: str, units: str = "") -> EnvelopeOutput:
        s = self.output_samples.get(name, np.array([0.0]))
        return EnvelopeOutput(
            mean=float(np.mean(s)),
            std=float(np.std(s)),
            percentiles={
                "p5": float(np.percentile(s, 5)),
                "p25": float(np.percentile(s, 25)),
                "p50": float(np.percentile(s, 50)),
                "p75": float(np.percentile(s, 75)),
                "p95": float(np.percentile(s, 95)),
            },
            units=units,
        )

    def probability_constraint_satisfied(self, output_name: str, threshold: float, direction: str = ">=") -> float:
        s = self.output_samples.get(output_name, np.array([0.0]))
        if direction == ">=":
            return float(np.mean(s >= threshold))
        elif direction == "<=":
            return float(np.mean(s <= threshold))
        return float(np.mean(s == threshold))

    def sensitivity_ranking(self, output_name: str, top_k: int = 10) -> list[SensitivityEntry]:
        """Rank inputs by correlation with output (fast sensitivity proxy)."""
        y = self.output_samples.get(output_name)
        if y is None:
            return []

        entries: list[SensitivityEntry] = []
        for iname, x in self.input_samples.items():
            if len(x) != len(y):
                continue
            corr = np.corrcoef(x, y)[0, 1] if np.std(x) > 1e-12 and np.std(y) > 1e-12 else 0.0
            entries.append(SensitivityEntry(
                parameter_name=iname,
                contribution_pct=abs(corr) * 100,
            ))

        entries.sort(key=lambda e: e.contribution_pct, reverse=True)
        return entries[:top_k]

    def sensitivity_ranking_mcp(
        self,
        constraint_outputs: list[str],
        top_k: int = 10,
    ) -> list[SensitivityEntry]:
        """Rank inputs by max correlation with any constraint output (MCP-relevant)."""
        if not constraint_outputs:
            return []

        entries_dict: dict[str, float] = {}
        for iname, x in self.input_samples.items():
            max_corr = 0.0
            for oname in constraint_outputs:
                y = self.output_samples.get(oname)
                if y is not None and len(x) == len(y) and np.std(x) > 1e-12 and np.std(y) > 1e-12:
                    corr = abs(np.corrcoef(x, y)[0, 1])
                    max_corr = max(max_corr, corr)
            entries_dict[iname] = max_corr * 100

        entries = [
            SensitivityEntry(parameter_name=iname, contribution_pct=pct)
            for iname, pct in entries_dict.items()
        ]
        entries.sort(key=lambda e: e.contribution_pct, reverse=True)
        return entries[:top_k]


class MonteCarloEngine:
    """Monte Carlo uncertainty propagation engine."""

    def __init__(self, n_samples: int = 1000, seed: int | None = None):
        self.n_samples = n_samples
        self.rng = np.random.default_rng(seed)

    def sample_inputs(
        self,
        inputs: list[MCInput],
        correlation_matrix: np.ndarray | None = None,
    ) -> dict[str, np.ndarray]:
        """Generate samples for all uncertain inputs."""
        samples: dict[str, np.ndarray] = {}

        if correlation_matrix is not None:
            specs = [inp.uncertainty for inp in inputs if inp.uncertainty is not None]
            names = [inp.name for inp in inputs if inp.uncertainty is not None]
            if specs and len(specs) == correlation_matrix.shape[0]:
                corr_samples = sample_correlated(specs, correlation_matrix, self.n_samples, self.rng)
                for i, name in enumerate(names):
                    samples[name] = corr_samples[:, i]

        for inp in inputs:
            if inp.name in samples:
                continue

            if inp.discrete_choices is not None:
                weights = inp.discrete_weights or [1.0 / len(inp.discrete_choices)] * len(inp.discrete_choices)
                weights_arr = np.array(weights) / sum(weights)
                samples[inp.name] = self.rng.choice(inp.discrete_choices, size=self.n_samples, p=weights_arr)
            elif inp.uncertainty is not None:
                samples[inp.name] = sample_from_spec(inp.uncertainty, self.n_samples, self.rng)
            else:
                samples[inp.name] = np.full(self.n_samples, inp.nominal)

        return samples

    def propagate(
        self,
        model_fn: Callable[[dict[str, float]], dict[str, float]],
        inputs: list[MCInput],
        correlation_matrix: np.ndarray | None = None,
    ) -> MCResult:
        """Run Monte Carlo propagation through a model function.

        model_fn: takes dict of input values, returns dict of output values.
        Only successful runs are kept; failed runs are dropped to ensure
        input/output alignment for sensitivity and constraint checks.
        """
        input_samples = self.sample_inputs(inputs, correlation_matrix)
        output_samples: dict[str, list[float]] = {}
        successful_inputs: dict[str, list[float]] = {name: [] for name in input_samples}

        for i in range(self.n_samples):
            input_dict = {name: float(samples[i]) for name, samples in input_samples.items()}
            try:
                outputs = model_fn(input_dict)
                for k, v in outputs.items():
                    if k not in output_samples:
                        output_samples[k] = []
                    output_samples[k].append(float(v))
                for name, samples in input_samples.items():
                    successful_inputs[name].append(float(samples[i]))
            except Exception:
                continue

        n_success = len(next(iter(output_samples.values()))) if output_samples else 0
        # When all runs fail, use empty arrays; otherwise filter inputs to successful runs only
        if n_success == 0:
            input_arrays = {k: np.array([], dtype=float) for k in input_samples}
        else:
            input_arrays = {k: np.array(v) for k, v in successful_inputs.items()}
        result = MCResult(
            input_samples=input_arrays,
            output_samples={k: np.array(v) for k, v in output_samples.items()},
            n_samples=n_success,
        )
        return result
