"""Unscented transform / sigma-point propagation for fast UQ.

Generates 2N+1 sigma points (Van der Merwe scaled UT), propagates through
the nonlinear model, recovers output mean + covariance without sampling
overhead.

Phase 2 changes:

* Non-PSD covariance is no longer silently regularised — callers get an
  :class:`InvalidCorrelationError` so they can repair the matrix
  intentionally (or pass ``allow_psd_jitter=True`` to opt into a known-good
  Higham-style bump).
* In strict mode (default), a model failure at a sigma point raises
  :class:`ModelEvaluationError` — the previous behaviour of dropping sigma
  points and renormalising weights is **not** a valid unscented transform
  and is only available when explicitly opted into.
* Missing outputs at sigma points raise :class:`MissingOutputError` instead
  of being silently treated as zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from gorzen.schemas.parameter import EnvelopeOutput
from gorzen.uq.errors import (
    InvalidCorrelationError,
    MissingOutputError,
    ModelEvaluationError,
)


@dataclass
class UTResult:
    """Results from unscented-transform uncertainty propagation."""

    output_mean: dict[str, float] = field(default_factory=dict)
    output_std: dict[str, float] = field(default_factory=dict)
    output_cov: np.ndarray | None = None
    n_sigma_points: int = 0
    sigma_point_evaluation_failures: int = 0
    """Count of sigma points where ``model_fn`` raised; those points are excluded and weights renormalized."""
    warnings: list[str] = field(default_factory=list)

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


class UnscentedTransform:
    """Unscented Transform for nonlinear uncertainty propagation.

    Uses Van der Merwe's scaled sigma point selection with tuning parameters
    alpha, beta, kappa.

    Args:
        alpha, beta, kappa: scaled UT tuning parameters.
        strict_model: When True (default), a model failure at any sigma
            point raises. Only set to False if the caller is prepared for
            the statistical bias introduced by dropping sigma points.
        allow_psd_jitter: When True, a non-PSD covariance is repaired by
            adding ``1e-8 I``. Default is False — callers must pass a
            well-conditioned matrix or raise :class:`InvalidCorrelationError`.
    """

    def __init__(
        self,
        alpha: float = 1e-3,
        beta: float = 2.0,
        kappa: float = 0.0,
        strict_model: bool = True,
        allow_psd_jitter: bool = False,
    ):
        self.alpha = alpha
        self.beta = beta
        self.kappa = kappa
        self.strict_model = strict_model
        self.allow_psd_jitter = allow_psd_jitter

    def _sigma_points(
        self, mean: np.ndarray, cov: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate sigma points and weights."""
        n = len(mean)
        lam = self.alpha**2 * (n + self.kappa) - n

        wm = np.full(2 * n + 1, 0.5 / (n + lam))
        wc = np.full(2 * n + 1, 0.5 / (n + lam))
        wm[0] = lam / (n + lam)
        wc[0] = lam / (n + lam) + (1 - self.alpha**2 + self.beta)

        try:
            sqrt_cov = np.linalg.cholesky((n + lam) * cov)
        except np.linalg.LinAlgError as exc:
            if self.allow_psd_jitter:
                sqrt_cov = np.linalg.cholesky((n + lam) * (cov + np.eye(n) * 1e-8))
            else:
                raise InvalidCorrelationError(
                    "UT covariance is not positive-definite — repair the input "
                    "covariance (e.g. Higham nearest-PSD) or pass "
                    "allow_psd_jitter=True to accept a 1e-8 I bump"
                ) from exc

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
        """Propagate uncertainty through model_fn using sigma points."""
        sigmas, wm, wc = self._sigma_points(param_means, param_cov)
        n_sigma = sigmas.shape[0]

        outputs_list: list[dict[str, float] | None] = []
        warnings: list[str] = []
        failures = 0
        for i in range(n_sigma):
            input_dict = {name: float(sigmas[i, j]) for j, name in enumerate(param_names)}
            try:
                out = model_fn(input_dict)
                outputs_list.append(out)
            except Exception as exc:
                if self.strict_model:
                    raise ModelEvaluationError(
                        f"UT sigma point {i}: {type(exc).__name__}: {exc}"
                    ) from exc
                failures += 1
                warnings.append(
                    f"sigma_point[{i}]: {type(exc).__name__}, excluded from UT statistics"
                )
                outputs_list.append(None)

        valid_idx = [i for i, o in enumerate(outputs_list) if o is not None]
        if not valid_idx:
            raise ModelEvaluationError("UT: all sigma-point evaluations failed")

        first = outputs_list[valid_idx[0]]
        assert first is not None
        out_names = list(first.keys())
        n_out = len(out_names)

        # Validate every sigma point returned the same output keys — otherwise
        # weights and indexing below would silently treat missing keys as 0.
        for i in valid_idx:
            out_dict = outputs_list[i]
            assert out_dict is not None
            missing = [n for n in out_names if n not in out_dict]
            if missing:
                raise MissingOutputError(missing[0], out_names)

        wm_f = np.array([wm[i] for i in valid_idx])
        wc_f = np.array([wc[i] for i in valid_idx])
        if failures > 0:
            # Opt-in behaviour only — strict_model=True raises earlier.
            wm_f = wm_f / wm_f.sum()
            wc_f = wc_f / wc_f.sum()

        n_valid = len(valid_idx)
        Y = np.zeros((n_valid, n_out))
        for row, i in enumerate(valid_idx):
            out_dict = outputs_list[i]
            assert out_dict is not None
            for j, name in enumerate(out_names):
                Y[row, j] = float(out_dict[name])

        y_mean = np.zeros(n_out)
        for row in range(n_valid):
            y_mean += wm_f[row] * Y[row]

        P_yy = np.zeros((n_out, n_out))
        for row in range(n_valid):
            dy = Y[row] - y_mean
            P_yy += wc_f[row] * np.outer(dy, dy)

        y_std = np.sqrt(np.maximum(np.diag(P_yy), 0.0))
        if failures > 0:
            warnings.append(
                f"UT: {failures}/{n_sigma} sigma points failed; mean/covariance used {n_valid} points with renormalized weights."
            )

        result = UTResult(
            output_mean={name: float(y_mean[j]) for j, name in enumerate(out_names)},
            output_std={name: float(y_std[j]) for j, name in enumerate(out_names)},
            output_cov=P_yy,
            n_sigma_points=n_sigma,
            sigma_point_evaluation_failures=failures,
            warnings=warnings,
        )
        return result
