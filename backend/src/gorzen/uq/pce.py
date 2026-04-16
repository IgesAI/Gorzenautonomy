"""Polynomial Chaos Expansion surrogate with Sobol sensitivity indices.

Phase 2 rewrite:

* Actually uses **Latin Hypercube** sampling (via ``scipy.stats.qmc``) for
  training — the previous version claimed LHS in the docstring but fell back
  to plain uniform random.
* Stops poisoning the least-squares fit with fabricated zero outputs when a
  model evaluation fails. In **strict** mode (default), the first failure
  raises :class:`ModelEvaluationError`; in tolerant mode failed rows are
  **dropped** from the regression (not replaced with zeros).
* Raises :class:`MissingOutputError` when a caller asks for an output the
  surrogate was never fitted on.
* Uses **Legendre polynomials orthogonal on [-1, 1] w.r.t. the uniform
  measure**, which is the right basis for PCE over uniform inputs. Variance
  contributions use the proper basis norms so Sobol indices match the
  analytical decomposition of the surrogate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from numpy.polynomial import legendre
from scipy.stats import qmc

from gorzen.schemas.parameter import EnvelopeOutput, SensitivityEntry
from gorzen.uq.errors import MissingOutputError, ModelEvaluationError


@dataclass
class PCEResult:
    """Results from PCE surrogate evaluation."""

    output_mean: dict[str, float] = field(default_factory=dict)
    output_std: dict[str, float] = field(default_factory=dict)
    sobol_first: dict[str, dict[str, float]] = field(default_factory=dict)
    sobol_total: dict[str, dict[str, float]] = field(default_factory=dict)

    def envelope_output(self, name: str, units: str = "") -> EnvelopeOutput:
        if name not in self.output_mean:
            raise MissingOutputError(name, list(self.output_mean.keys()))
        m = self.output_mean[name]
        s = self.output_std.get(name, 0.0)
        return EnvelopeOutput(
            mean=m,
            std=s,
            percentiles={
                "p5": m - 1.645 * s,
                "p25": m - 0.674 * s,
                "p50": m,
                "p75": m + 0.674 * s,
                "p95": m + 1.645 * s,
            },
            units=units,
        )

    def sensitivity_entries(self, output_name: str, top_k: int = 10) -> list[SensitivityEntry]:
        if output_name not in self.sobol_first:
            raise MissingOutputError(output_name, list(self.sobol_first.keys()))
        first = self.sobol_first[output_name]
        total = self.sobol_total.get(output_name, {})
        entries: list[SensitivityEntry] = []
        for pname, s1 in first.items():
            entries.append(
                SensitivityEntry(
                    parameter_name=pname,
                    sobol_first_order=s1,
                    sobol_total=total.get(pname),
                    contribution_pct=s1 * 100,
                )
            )
        entries.sort(key=lambda e: e.contribution_pct, reverse=True)
        return entries[:top_k]


def _multiindex_set(n_dim: int, max_order: int) -> list[tuple[int, ...]]:
    """Generate multi-index set for total-degree truncation."""
    if n_dim == 0:
        return [()]
    if n_dim == 1:
        return [(i,) for i in range(max_order + 1)]

    indices: list[tuple[int, ...]] = []
    for total in range(max_order + 1):
        for sub in _multiindex_set(n_dim - 1, total):
            remainder = total - sum(sub)
            if remainder >= 0:
                indices.append(sub + (remainder,))
    return indices


def _legendre_uniform_basis_variance_weight(midx: tuple[int, ...]) -> float:
    """Variance contribution weight for tensor Legendre basis under Uniform(-1,1) per axis.

    For independent Uniform(-1,1) inputs, E[P_{α_1}(X_1)^2 ...] = ∏_d 1/(2α_d+1)
    with numpy's Legendre polynomials (orthogonal on [-1,1] w.r.t. uniform measure).
    """
    w = 1.0
    for order in midx:
        w /= float(2 * order + 1)
    return w


class PCESurrogate:
    """Polynomial Chaos Expansion surrogate using Legendre polynomials.

    Assumes inputs are normalized to [-1, 1] (uniform measure). Uses
    least-squares regression against **Latin Hypercube** training points.
    """

    def __init__(
        self,
        max_order: int = 3,
        n_training_factor: int = 2,
        strict_model: bool = True,
        seed: int | None = 42,
    ):
        self.max_order = max_order
        self.n_training_factor = n_training_factor
        self.strict_model = strict_model
        self.seed = seed
        self.coefficients: dict[str, np.ndarray] = {}
        self.multi_indices: list[tuple[int, ...]] = []
        self.param_names: list[str] = []
        self.fit_evaluation_failures: int = 0
        """Training samples where ``model_fn`` raised; in tolerant mode those rows are dropped from the regression."""
        self.fit_rows_used: int = 0
        """Number of training rows actually used after dropping failures."""

    def _evaluate_basis(self, x: np.ndarray) -> np.ndarray:
        """Evaluate all basis polynomials at sample points.

        x: shape (n_samples, n_dim), values in [-1, 1]
        Returns: shape (n_samples, n_basis)
        """
        n_samples = x.shape[0]
        n_basis = len(self.multi_indices)
        Phi = np.ones((n_samples, n_basis))

        for j, midx in enumerate(self.multi_indices):
            for d, order in enumerate(midx):
                if order > 0:
                    coeffs = [0.0] * order + [1.0]
                    Phi[:, j] *= legendre.legval(x[:, d], coeffs)
        return Phi

    def fit(
        self,
        model_fn: Callable[[dict[str, float]], dict[str, float]],
        param_names: list[str],
        param_bounds: list[tuple[float, float]],
    ) -> None:
        """Fit the PCE surrogate from model evaluations using LHS training points."""
        self.param_names = param_names
        self.fit_evaluation_failures = 0
        self.fit_rows_used = 0
        n_dim = len(param_names)
        self.multi_indices = _multiindex_set(n_dim, self.max_order)
        n_basis = len(self.multi_indices)
        n_samples = max(n_basis * self.n_training_factor, 20)

        sampler = qmc.LatinHypercube(d=n_dim, seed=self.seed)
        u = sampler.random(n_samples)
        x_norm = 2 * u - 1  # unit cube -> [-1, 1]^n_dim

        # Map to physical space
        x_phys = np.zeros_like(x_norm)
        for d in range(n_dim):
            lo, hi = param_bounds[d]
            x_phys[:, d] = lo + (x_norm[:, d] + 1) / 2 * (hi - lo)

        # Evaluate model
        out_rows: list[dict[str, float]] = []
        valid_rows: list[int] = []
        for i in range(n_samples):
            inp = {name: float(x_phys[i, j]) for j, name in enumerate(param_names)}
            try:
                out = model_fn(inp)
            except Exception as exc:
                if self.strict_model:
                    raise ModelEvaluationError(
                        f"PCE training sample {i}: {type(exc).__name__}: {exc}"
                    ) from exc
                self.fit_evaluation_failures += 1
                continue
            out_rows.append(out)
            valid_rows.append(i)

        if not out_rows:
            raise ModelEvaluationError(
                "PCE fit: every training sample failed — refusing to build a surrogate from nothing"
            )

        out_names = sorted({k for row in out_rows for k in row.keys()})
        missing_any = False
        Y = np.zeros((len(out_rows), len(out_names)))
        for i, row in enumerate(out_rows):
            for j, name in enumerate(out_names):
                if name not in row:
                    missing_any = True
                    Y[i, j] = np.nan
                else:
                    Y[i, j] = float(row[name])

        # Drop rows that have any NaN (partial outputs) — the least-squares
        # fit would otherwise be polluted by zeros masquerading as signal.
        good_mask = ~np.isnan(Y).any(axis=1)
        if not good_mask.all():
            if self.strict_model:
                raise ModelEvaluationError(
                    "PCE fit: training rows produced inconsistent output sets; "
                    "every sample must return the same output keys in strict mode"
                )
            Y = Y[good_mask]
            valid_rows = [r for r, ok in zip(valid_rows, good_mask, strict=False) if ok]

        if Y.shape[0] < n_basis:
            raise ModelEvaluationError(
                f"PCE fit: {Y.shape[0]} usable training rows is below basis size {n_basis}; "
                "regression is under-determined."
            )

        Phi = self._evaluate_basis(x_norm[valid_rows])
        self.fit_rows_used = len(valid_rows)

        for j, oname in enumerate(out_names):
            coeffs, _, _, _ = np.linalg.lstsq(Phi, Y[:, j], rcond=None)
            self.coefficients[oname] = coeffs
        # Suppress unused-variable warning on missing_any — it's informative
        # in strict mode, which already raised above.
        del missing_any

    def predict(self, x_norm: np.ndarray) -> dict[str, np.ndarray]:
        """Predict outputs at normalized points."""
        Phi = self._evaluate_basis(x_norm)
        results: dict[str, np.ndarray] = {}
        for oname, coeffs in self.coefficients.items():
            results[oname] = Phi @ coeffs
        return results

    def compute_statistics(self) -> PCEResult:
        """Compute mean, variance, and Sobol indices from PCE coefficients."""
        result = PCEResult()

        for oname, coeffs in self.coefficients.items():
            result.output_mean[oname] = float(coeffs[0])

            var_terms = [
                float(coeffs[j] ** 2 * _legendre_uniform_basis_variance_weight(midx))
                for j, midx in enumerate(self.multi_indices)
                if j > 0
            ]
            variance = float(np.sum(var_terms)) if var_terms else 0.0
            result.output_std[oname] = float(np.sqrt(max(variance, 0)))

            if variance > 1e-12:
                first_order: dict[str, float] = {}
                total_order: dict[str, float] = {}

                for d, pname in enumerate(self.param_names):
                    s1 = 0.0
                    st = 0.0
                    for j, midx in enumerate(self.multi_indices):
                        if j == 0:
                            continue
                        wj = coeffs[j] ** 2 * _legendre_uniform_basis_variance_weight(midx)
                        if midx[d] > 0:
                            st += wj
                            if all(midx[k] == 0 for k in range(len(midx)) if k != d):
                                s1 += wj
                    first_order[pname] = s1 / variance
                    total_order[pname] = st / variance

                result.sobol_first[oname] = first_order
                result.sobol_total[oname] = total_order

        return result
