"""Monte Carlo sampling engine with QMC (Sobol' / Latin Hypercube) sampling
and optional Saltelli sampling for true Sobol indices.

Baseline truth engine: handles arbitrary nonlinearities, discrete choices,
and mixed distributions. After Phase 2 of the backend audit this module:

* Prefers **Sobol'** (or LHS) sampling via ``scipy.stats.qmc`` for much better
  coverage of the input space than plain IID random draws.
* Raises :class:`MissingOutputError` when a consumer requests an output that
  was never produced — instead of silently fabricating a degenerate
  ``np.array([0.0])`` sample.
* Lets callers choose **strict mode** (any model exception aborts the run) or
  **tolerant mode** (failures are counted and reported with warnings, but are
  not hidden).
* Exposes a **Saltelli** extension for real first-order and total-effect
  Sobol' indices — the Pearson-correlation "sensitivity" from before is kept
  as a cheap fallback, but Saltelli is recommended for mission-critical
  decisions.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Callable, Literal

import numpy as np
from scipy.stats import qmc

from gorzen.schemas.parameter import EnvelopeOutput, SensitivityEntry, UncertaintySpec
from gorzen.uq.distributions import sample_correlated, sample_from_spec
from gorzen.uq.errors import MissingOutputError, ModelEvaluationError

logger = logging.getLogger(__name__)


SamplingStrategy = Literal["iid", "sobol", "lhs"]


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
    """Number of successful model evaluations (aligned output rows)."""
    n_attempted: int = 0
    """Total trials (equals engine n_samples when all inputs valid)."""
    n_failed: int = 0
    """Model evaluations that raised or returned unusable output (dropped)."""
    sampling_strategy: SamplingStrategy = "iid"

    def _require(self, name: str) -> np.ndarray:
        if name not in self.output_samples:
            raise MissingOutputError(name, list(self.output_samples.keys()))
        return self.output_samples[name]

    def envelope_output(self, name: str, units: str = "") -> EnvelopeOutput:
        """Return mean / std / percentiles for ``name``.

        Raises :class:`MissingOutputError` if ``name`` was never produced —
        callers must handle missing outputs explicitly (no silent zeros).
        """
        s = self._require(name)
        if s.size == 0:
            # All evaluations failed. Report NaNs so downstream code can't
            # mistake this for a real measurement.
            return EnvelopeOutput(
                mean=float("nan"),
                std=float("nan"),
                percentiles={"p5": float("nan"), "p25": float("nan"), "p50": float("nan"),
                             "p75": float("nan"), "p95": float("nan")},
                units=units,
            )
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

    def probability_constraint_satisfied(
        self, output_name: str, threshold: float, direction: str = ">="
    ) -> float:
        s = self._require(output_name)
        if s.size == 0:
            return 0.0
        if direction == ">=":
            return float(np.mean(s >= threshold))
        if direction == "<=":
            return float(np.mean(s <= threshold))
        return float(np.mean(s == threshold))

    def sensitivity_ranking(self, output_name: str, top_k: int = 10) -> list[SensitivityEntry]:
        """Rank inputs by Pearson correlation with output (cheap proxy).

        For rigorous Sobol' first-order / total indices, see
        :meth:`MonteCarloEngine.saltelli_sobol`.
        """
        if output_name not in self.output_samples:
            raise MissingOutputError(output_name, list(self.output_samples.keys()))
        y = self.output_samples[output_name]
        entries: list[SensitivityEntry] = []
        for iname, x in self.input_samples.items():
            if len(x) != len(y):
                continue
            if np.std(x) > 1e-12 and np.std(y) > 1e-12:
                corr = float(np.corrcoef(x, y)[0, 1])
            else:
                # Zero-variance input (or output) cannot be ranked by correlation;
                # drop it rather than pretending its contribution is zero.
                continue
            entries.append(
                SensitivityEntry(
                    parameter_name=iname,
                    contribution_pct=abs(corr) * 100,
                )
            )

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

        missing = [c for c in constraint_outputs if c not in self.output_samples]
        if missing:
            raise MissingOutputError(missing[0], list(self.output_samples.keys()))

        entries_dict: dict[str, float] = {}
        for iname, x in self.input_samples.items():
            max_corr = 0.0
            for oname in constraint_outputs:
                y = self.output_samples[oname]
                if len(x) == len(y) and np.std(x) > 1e-12 and np.std(y) > 1e-12:
                    corr = abs(np.corrcoef(x, y)[0, 1])
                    if corr > max_corr:
                        max_corr = float(corr)
            if max_corr > 0:
                entries_dict[iname] = max_corr * 100

        entries = [
            SensitivityEntry(parameter_name=iname, contribution_pct=pct)
            for iname, pct in entries_dict.items()
        ]
        entries.sort(key=lambda e: e.contribution_pct, reverse=True)
        return entries[:top_k]


class MonteCarloEngine:
    """Monte Carlo uncertainty propagation engine.

    Args:
        n_samples: Number of samples to draw.
        seed: RNG seed (None = non-deterministic).
        sampling: ``"sobol"`` (default) for low-discrepancy Sobol', ``"lhs"``
            for Latin Hypercube, or ``"iid"`` for plain random.
        strict_model: When True, any exception raised by the model function
            aborts the entire run with :class:`ModelEvaluationError`. When
            False (default), failures are counted and dropped — suitable for
            rare constraint violations where the failure itself is informative.
    """

    def __init__(
        self,
        n_samples: int = 1000,
        seed: int | None = 42,
        sampling: SamplingStrategy = "sobol",
        strict_model: bool = False,
    ):
        self.n_samples = n_samples
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.sampling = sampling
        self.strict_model = strict_model

    # -- sampling ------------------------------------------------------------

    def _unit_samples(self, n_dim: int) -> np.ndarray:
        """Draw shape (n_samples, n_dim) in the open hypercube (0, 1)^n_dim."""
        if self.sampling == "sobol":
            sampler = qmc.Sobol(d=n_dim, scramble=True, seed=self.seed)
            # scipy warns when ``n_samples`` is not a power of 2 (balance
            # properties). Our engine lets callers pick any n; suppress the
            # warning — they've been told to prefer LHS if perfect balance
            # matters.
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="The balance properties of Sobol",
                    category=UserWarning,
                )
                return sampler.random(self.n_samples)
        if self.sampling == "lhs":
            sampler = qmc.LatinHypercube(d=n_dim, seed=self.seed)
            return sampler.random(self.n_samples)
        return self.rng.random((self.n_samples, n_dim))

    def sample_inputs(
        self,
        inputs: list[MCInput],
        correlation_matrix: np.ndarray | None = None,
    ) -> dict[str, np.ndarray]:
        """Generate samples for all uncertain inputs.

        Correlated inputs are drawn via a Gaussian copula (see
        :func:`sample_correlated`); independent continuous inputs are drawn
        via inverse-CDF on low-discrepancy unit samples so Sobol' / LHS
        coverage is preserved through the marginal transform.
        """
        samples: dict[str, np.ndarray] = {}

        if correlation_matrix is not None:
            specs = [inp.uncertainty for inp in inputs if inp.uncertainty is not None]
            names = [inp.name for inp in inputs if inp.uncertainty is not None]
            if specs and len(specs) == correlation_matrix.shape[0]:
                corr_samples = sample_correlated(
                    specs, correlation_matrix, self.n_samples, self.rng
                )
                for i, name in enumerate(names):
                    samples[name] = corr_samples[:, i]

        # Continuous inputs go through the unit-cube sampler so QMC carries
        # through the inverse-CDF transform; discrete inputs use the rng
        # directly.
        continuous = [
            inp for inp in inputs if inp.name not in samples and inp.discrete_choices is None
        ]
        if continuous:
            u = self._unit_samples(len(continuous))
            for i, inp in enumerate(continuous):
                if inp.uncertainty is not None:
                    from gorzen.uq.distributions import inverse_cdf_from_unit
                    samples[inp.name] = inverse_cdf_from_unit(inp.uncertainty, u[:, i])
                else:
                    samples[inp.name] = np.full(self.n_samples, inp.nominal)

        for inp in inputs:
            if inp.name in samples:
                continue
            if inp.discrete_choices is not None:
                weights = inp.discrete_weights or [1.0 / len(inp.discrete_choices)] * len(
                    inp.discrete_choices
                )
                weights_arr = np.array(weights) / sum(weights)
                samples[inp.name] = self.rng.choice(
                    inp.discrete_choices, size=self.n_samples, p=weights_arr
                )
            elif inp.uncertainty is not None:
                samples[inp.name] = sample_from_spec(inp.uncertainty, self.n_samples, self.rng)
            else:
                samples[inp.name] = np.full(self.n_samples, inp.nominal)

        return samples

    # -- propagation ---------------------------------------------------------

    def propagate(
        self,
        model_fn: Callable[[dict[str, float]], dict[str, float]],
        inputs: list[MCInput],
        correlation_matrix: np.ndarray | None = None,
    ) -> MCResult:
        """Run Monte Carlo propagation through a model function.

        Only successful runs are kept; failed runs are dropped to ensure
        input/output alignment for sensitivity and constraint checks. Under
        ``strict_model=True`` the first failure is raised instead.
        """
        input_samples = self.sample_inputs(inputs, correlation_matrix)
        output_samples: dict[str, list[float]] = {}
        successful_inputs: dict[str, list[float]] = {name: [] for name in input_samples}

        n_failed = 0
        failure_summary: dict[str, int] = {}
        for i in range(self.n_samples):
            input_dict = {name: float(samples[i]) for name, samples in input_samples.items()}
            try:
                outputs = model_fn(input_dict)
            except Exception as exc:
                if self.strict_model:
                    raise ModelEvaluationError(
                        f"Monte Carlo sample {i}: {type(exc).__name__}: {exc}"
                    ) from exc
                n_failed += 1
                key = type(exc).__name__
                failure_summary[key] = failure_summary.get(key, 0) + 1
                continue

            for k, v in outputs.items():
                output_samples.setdefault(k, []).append(float(v))
            for name, samples in input_samples.items():
                successful_inputs[name].append(float(samples[i]))

        if failure_summary:
            summary = ", ".join(f"{k}={v}" for k, v in sorted(failure_summary.items()))
            logger.warning("Monte Carlo failures: %s", summary)

        n_success = len(next(iter(output_samples.values()))) if output_samples else 0
        if n_success == 0:
            input_arrays = {k: np.array([], dtype=float) for k in input_samples}
        else:
            input_arrays = {k: np.array(v) for k, v in successful_inputs.items()}
        return MCResult(
            input_samples=input_arrays,
            output_samples={k: np.array(v) for k, v in output_samples.items()},
            n_samples=n_success,
            n_attempted=self.n_samples,
            n_failed=n_failed,
            sampling_strategy=self.sampling,
        )

    # -- Saltelli Sobol' indices --------------------------------------------

    def saltelli_sobol(
        self,
        model_fn: Callable[[dict[str, float]], dict[str, float]],
        inputs: list[MCInput],
        output_name: str,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Compute Saltelli first-order (S1) and total-effect (ST) Sobol' indices.

        This is O((d+2)·N) model evaluations for ``d`` inputs and base sample
        size ``N = self.n_samples``. Use when you need rigorous global
        sensitivity; for a cheap sanity check use
        :meth:`MCResult.sensitivity_ranking`.

        Returns two dicts keyed by input name: ``S1[name]`` and ``ST[name]``.
        """
        continuous = [inp for inp in inputs if inp.discrete_choices is None]
        if not continuous:
            raise ValueError("Saltelli sampling requires at least one continuous input")
        d = len(continuous)
        names = [inp.name for inp in continuous]

        sampler = qmc.Sobol(d=2 * d, scramble=True, seed=self.seed)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="The balance properties of Sobol",
                category=UserWarning,
            )
            u = sampler.random(self.n_samples)
        a = u[:, :d]
        b = u[:, d:]

        def _map_to_physical(unit: np.ndarray) -> np.ndarray:
            phys = np.zeros_like(unit)
            from gorzen.uq.distributions import inverse_cdf_from_unit
            for j, inp in enumerate(continuous):
                if inp.uncertainty is None:
                    phys[:, j] = inp.nominal
                else:
                    phys[:, j] = inverse_cdf_from_unit(inp.uncertainty, unit[:, j])
            return phys

        A = _map_to_physical(a)
        B = _map_to_physical(b)

        def eval_matrix(X: np.ndarray) -> np.ndarray:
            y = np.zeros(self.n_samples)
            for i in range(self.n_samples):
                inp_dict = {n: float(X[i, j]) for j, n in enumerate(names)}
                try:
                    out = model_fn(inp_dict)
                except Exception as exc:
                    if self.strict_model:
                        raise ModelEvaluationError(
                            f"Saltelli evaluation failed: {exc}"
                        ) from exc
                    y[i] = np.nan
                    continue
                if output_name not in out:
                    raise MissingOutputError(output_name, list(out.keys()))
                y[i] = float(out[output_name])
            return y

        yA = eval_matrix(A)
        yB = eval_matrix(B)

        S1: dict[str, float] = {}
        ST: dict[str, float] = {}
        varY = float(np.nanvar(np.concatenate([yA, yB])))
        if varY < 1e-20:
            # Output is effectively constant — all indices are zero.
            for n in names:
                S1[n] = 0.0
                ST[n] = 0.0
            return S1, ST

        for j, n in enumerate(names):
            AB = A.copy()
            AB[:, j] = B[:, j]
            yAB = eval_matrix(AB)
            # Saltelli 2010 estimators (Jansen-style).
            s1_num = float(np.nanmean(yB * (yAB - yA)))
            st_num = float(0.5 * np.nanmean((yA - yAB) ** 2))
            S1[n] = max(0.0, s1_num / varY)
            ST[n] = max(0.0, st_num / varY)

        return S1, ST
