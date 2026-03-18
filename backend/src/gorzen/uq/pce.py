"""Polynomial Chaos Expansion surrogate with Sobol sensitivity indices.

Builds a PCE surrogate for smooth response surfaces, enabling fast evaluation
of moments, quantiles, and global sensitivity analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from numpy.polynomial import legendre

from gorzen.schemas.parameter import EnvelopeOutput, SensitivityEntry


@dataclass
class PCEResult:
    """Results from PCE surrogate evaluation."""

    output_mean: dict[str, float] = field(default_factory=dict)
    output_std: dict[str, float] = field(default_factory=dict)
    sobol_first: dict[str, dict[str, float]] = field(default_factory=dict)
    sobol_total: dict[str, dict[str, float]] = field(default_factory=dict)

    def envelope_output(self, name: str, units: str = "") -> EnvelopeOutput:
        m = self.output_mean.get(name, 0.0)
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
        first = self.sobol_first.get(output_name, {})
        total = self.sobol_total.get(output_name, {})
        entries = []
        for pname in first:
            entries.append(SensitivityEntry(
                parameter_name=pname,
                sobol_first_order=first.get(pname),
                sobol_total=total.get(pname),
                contribution_pct=first.get(pname, 0.0) * 100,
            ))
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


class PCESurrogate:
    """Polynomial Chaos Expansion surrogate using Legendre polynomials.

    Assumes inputs are normalized to [-1, 1] (uniform) or transformed appropriately.
    Uses least-squares regression to fit coefficients from model evaluations.
    """

    def __init__(self, max_order: int = 3, n_training_factor: int = 2):
        self.max_order = max_order
        self.n_training_factor = n_training_factor
        self.coefficients: dict[str, np.ndarray] = {}
        self.multi_indices: list[tuple[int, ...]] = []
        self.param_names: list[str] = []

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
        """Fit the PCE surrogate from model evaluations.

        Generates Latin Hypercube samples in normalized space, evaluates model,
        and solves least-squares for PCE coefficients.
        """
        self.param_names = param_names
        n_dim = len(param_names)
        self.multi_indices = _multiindex_set(n_dim, self.max_order)
        n_basis = len(self.multi_indices)
        n_samples = max(n_basis * self.n_training_factor, 20)

        rng = np.random.default_rng(42)
        x_norm = rng.uniform(-1, 1, (n_samples, n_dim))

        # Map to physical space
        x_phys = np.zeros_like(x_norm)
        for d in range(n_dim):
            lo, hi = param_bounds[d]
            x_phys[:, d] = lo + (x_norm[:, d] + 1) / 2 * (hi - lo)

        # Evaluate model
        outputs_list: list[dict[str, float]] = []
        for i in range(n_samples):
            inp = {name: float(x_phys[i, j]) for j, name in enumerate(param_names)}
            try:
                out = model_fn(inp)
            except Exception:
                out = {}
            outputs_list.append(out)

        if not outputs_list:
            return

        out_names = list(outputs_list[0].keys())
        Y = np.zeros((n_samples, len(out_names)))
        for i, out in enumerate(outputs_list):
            for j, name in enumerate(out_names):
                Y[i, j] = out.get(name, 0.0)

        # Build Vandermonde-like matrix
        Phi = self._evaluate_basis(x_norm)

        # Least-squares fit
        for j, oname in enumerate(out_names):
            coeffs, _, _, _ = np.linalg.lstsq(Phi, Y[:, j], rcond=None)
            self.coefficients[oname] = coeffs

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
            # Mean is the first coefficient (constant term)
            result.output_mean[oname] = float(coeffs[0])

            # Variance from non-constant coefficients
            variance = float(np.sum(coeffs[1:] ** 2))
            result.output_std[oname] = float(np.sqrt(max(variance, 0)))

            # First-order Sobol indices
            if variance > 1e-12:
                first_order: dict[str, float] = {}
                total_order: dict[str, float] = {}

                for d, pname in enumerate(self.param_names):
                    # Indices where only dimension d has nonzero order
                    s1 = 0.0
                    st = 0.0
                    for j, midx in enumerate(self.multi_indices):
                        if j == 0:
                            continue
                        if midx[d] > 0:
                            st += coeffs[j] ** 2
                            if all(midx[k] == 0 for k in range(len(midx)) if k != d):
                                s1 += coeffs[j] ** 2
                    first_order[pname] = s1 / variance
                    total_order[pname] = st / variance

                result.sobol_first[oname] = first_order
                result.sobol_total[oname] = total_order

        return result
