"""Unscented transform / sigma-point propagation for fast UQ.

Generates 2N+1 sigma points, propagates through nonlinear model,
recovers output mean + covariance without sampling overhead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from gorzen.schemas.parameter import EnvelopeOutput


@dataclass
class UTResult:
    """Results from unscented-transform uncertainty propagation."""

    output_mean: dict[str, float] = field(default_factory=dict)
    output_std: dict[str, float] = field(default_factory=dict)
    output_cov: np.ndarray | None = None
    n_sigma_points: int = 0

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


class UnscentedTransform:
    """Unscented Transform for nonlinear uncertainty propagation.

    Uses Van der Merwe's scaled sigma point selection with tuning parameters
    alpha, beta, kappa.
    """

    def __init__(
        self,
        alpha: float = 1e-3,
        beta: float = 2.0,
        kappa: float = 0.0,
    ):
        self.alpha = alpha
        self.beta = beta
        self.kappa = kappa

    def _sigma_points(
        self, mean: np.ndarray, cov: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate sigma points and weights."""
        n = len(mean)
        lam = self.alpha**2 * (n + self.kappa) - n

        # Weights
        wm = np.full(2 * n + 1, 0.5 / (n + lam))
        wc = np.full(2 * n + 1, 0.5 / (n + lam))
        wm[0] = lam / (n + lam)
        wc[0] = lam / (n + lam) + (1 - self.alpha**2 + self.beta)

        # Sigma points
        try:
            sqrt_cov = np.linalg.cholesky((n + lam) * cov)
        except np.linalg.LinAlgError:
            sqrt_cov = np.linalg.cholesky((n + lam) * (cov + np.eye(n) * 1e-8))

        sigmas = np.zeros((2 * n + 1, n))
        sigmas[0] = mean
        for i in range(n):
            sigmas[i + 1] = mean + sqrt_cov[:, i]
            sigmas[n + i + 1] = mean - sqrt_cov[:, i]

        return sigmas, wm, wc

    def propagate(
        self,
        model_fn: Callable[[dict[str, float]], dict[str, float]],
        param_names: list[str],
        param_means: np.ndarray,
        param_cov: np.ndarray,
    ) -> UTResult:
        """Propagate uncertainty through model_fn using sigma points.

        model_fn: dict[str,float] -> dict[str,float]
        """
        sigmas, wm, wc = self._sigma_points(param_means, param_cov)
        n_sigma = sigmas.shape[0]

        # Evaluate model at each sigma point
        outputs_list: list[dict[str, float]] = []
        for i in range(n_sigma):
            input_dict = {name: float(sigmas[i, j]) for j, name in enumerate(param_names)}
            try:
                out = model_fn(input_dict)
            except Exception:
                out = model_fn({name: float(param_means[j]) for j, name in enumerate(param_names)})
            outputs_list.append(out)

        # Collect output names from first evaluation
        out_names = list(outputs_list[0].keys())
        n_out = len(out_names)

        # Build output matrix
        Y = np.zeros((n_sigma, n_out))
        for i, out_dict in enumerate(outputs_list):
            for j, name in enumerate(out_names):
                Y[i, j] = out_dict.get(name, 0.0)

        # Weighted mean
        y_mean = np.zeros(n_out)
        for i in range(n_sigma):
            y_mean += wm[i] * Y[i]

        # Weighted covariance
        P_yy = np.zeros((n_out, n_out))
        for i in range(n_sigma):
            dy = Y[i] - y_mean
            P_yy += wc[i] * np.outer(dy, dy)

        y_std = np.sqrt(np.maximum(np.diag(P_yy), 0.0))

        result = UTResult(
            output_mean={name: float(y_mean[j]) for j, name in enumerate(out_names)},
            output_std={name: float(y_std[j]) for j, name in enumerate(out_names)},
            output_cov=P_yy,
            n_sigma_points=n_sigma,
        )
        return result
