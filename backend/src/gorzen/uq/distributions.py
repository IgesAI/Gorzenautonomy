"""Distribution types, correlation groups, and evidence binding for UQ.

Phase 2 notes:

* ``make_scipy_dist`` now raises :class:`MissingUncertaintyError` when a
  distribution is missing parameters required to construct it — previously a
  missing ``std`` silently defaulted to ``1.0``.
* ``sample_correlated`` validates that the correlation matrix is symmetric
  positive-definite; non-PSD matrices now raise
  :class:`InvalidCorrelationError` instead of tripping a cryptic Cholesky
  failure later in the pipeline.
* A new :func:`inverse_cdf_from_unit` drives Sobol' / LHS sampling so
  quasi-random coverage survives the marginal transform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats

from gorzen.schemas.parameter import DistributionType, UncertaintySpec
from gorzen.uq.errors import InvalidCorrelationError, MissingUncertaintyError


@dataclass
class CorrelationGroup:
    """A group of parameters that are correlated."""

    group_id: str
    parameter_names: list[str] = field(default_factory=list)
    correlation_matrix: np.ndarray | None = None

    def set_correlation(self, corr: np.ndarray) -> None:
        assert corr.shape == (len(self.parameter_names), len(self.parameter_names))
        self.correlation_matrix = corr


@dataclass
class EvidenceBinding:
    """Links a distribution to the evidence that supports it."""

    parameter_name: str
    log_ids: list[str] = field(default_factory=list)
    test_ids: list[str] = field(default_factory=list)
    n_observations: int = 0
    last_updated: str = ""


def _require_param(p: dict, name: str, dist_label: str) -> float:
    if name not in p:
        raise MissingUncertaintyError(
            f"{dist_label} distribution is missing required parameter {name!r}"
        )
    return float(p[name])


def make_scipy_dist(spec: UncertaintySpec) -> Any:
    """Convert an UncertaintySpec into a scipy frozen distribution (rv_frozen).

    Required parameters are enforced per distribution type:

    * NORMAL:      ``mean``, ``std``
    * UNIFORM:     ``low``, ``high``
    * BETA:        ``a``, ``b``
    * LOGNORMAL:   ``mu``, ``sigma``
    * TRIANGULAR:  ``low``, ``mode``, ``high``
    * WEIBULL:     ``shape`` (``scale`` optional, defaults to 1)
    """
    p = spec.params
    dt = spec.distribution

    if dt == DistributionType.NORMAL:
        return stats.norm(
            loc=_require_param(p, "mean", "Normal"),
            scale=_require_param(p, "std", "Normal"),
        )
    if dt == DistributionType.UNIFORM:
        lo = _require_param(p, "low", "Uniform")
        hi = _require_param(p, "high", "Uniform")
        if hi <= lo:
            raise MissingUncertaintyError(f"Uniform distribution requires high>low (got {lo}, {hi})")
        return stats.uniform(loc=lo, scale=hi - lo)
    if dt == DistributionType.BETA:
        return stats.beta(
            a=_require_param(p, "a", "Beta"),
            b=_require_param(p, "b", "Beta"),
        )
    if dt == DistributionType.LOGNORMAL:
        return stats.lognorm(
            s=_require_param(p, "sigma", "Lognormal"),
            scale=np.exp(_require_param(p, "mu", "Lognormal")),
        )
    if dt == DistributionType.TRIANGULAR:
        lo = _require_param(p, "low", "Triangular")
        mode = _require_param(p, "mode", "Triangular")
        hi = _require_param(p, "high", "Triangular")
        if not (lo <= mode <= hi) or hi == lo:
            raise MissingUncertaintyError(
                f"Triangular requires low <= mode <= high with hi>lo (got {lo}, {mode}, {hi})"
            )
        c = (mode - lo) / (hi - lo)
        return stats.triang(c=c, loc=lo, scale=hi - lo)
    if dt == DistributionType.WEIBULL:
        return stats.weibull_min(
            c=_require_param(p, "shape", "Weibull"),
            scale=float(p.get("scale", 1.0)),
        )
    if dt == DistributionType.EMPIRICAL:
        raise ValueError("Empirical distributions require sample data, not a parametric spec.")
    raise MissingUncertaintyError(f"Unsupported distribution type: {dt}")


def sample_from_spec(
    spec: UncertaintySpec,
    n: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Draw n samples from an UncertaintySpec. Uses fixed seed when rng is None for determinism."""
    gen: np.random.Generator = rng if rng is not None else np.random.default_rng(42)

    dist = make_scipy_dist(spec)
    raw = dist.rvs(size=n, random_state=gen.integers(0, 2**31))
    samples = np.asarray(raw, dtype=np.float64)

    if spec.bounds is not None:
        lo, hi = spec.bounds
        samples = np.clip(samples, lo, hi)

    return samples


def _validate_correlation(corr: np.ndarray, k: int) -> None:
    if corr.shape != (k, k):
        raise InvalidCorrelationError(
            f"Correlation matrix shape {corr.shape} does not match {k} specs"
        )
    if not np.allclose(corr, corr.T, atol=1e-8):
        raise InvalidCorrelationError("Correlation matrix must be symmetric")
    diag = np.diag(corr)
    if not np.allclose(diag, 1.0, atol=1e-6):
        raise InvalidCorrelationError(f"Correlation matrix diagonal must be 1.0 (got {diag})")
    try:
        eig = np.linalg.eigvalsh(corr)
    except np.linalg.LinAlgError as exc:
        raise InvalidCorrelationError(f"eigen decomposition failed: {exc}") from exc
    if eig.min() < -1e-8:
        raise InvalidCorrelationError(
            f"Correlation matrix is not positive semi-definite (min eigenvalue {eig.min():.3g}); "
            "repair with a nearest-PSD projection (e.g. Higham) before passing in."
        )


def sample_correlated(
    specs: list[UncertaintySpec],
    correlation_matrix: np.ndarray,
    n: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Draw correlated samples from multiple specs using Gaussian copula.

    Returns shape (n, len(specs)). Uses fixed seed when rng is None for
    determinism. Raises :class:`InvalidCorrelationError` if the supplied
    matrix is not a valid correlation matrix.
    """
    gen: np.random.Generator = rng if rng is not None else np.random.default_rng(42)

    k = len(specs)
    _validate_correlation(correlation_matrix, k)

    # Generate correlated standard normals
    L = np.linalg.cholesky(correlation_matrix)
    z = gen.standard_normal((n, k)) @ L.T

    # Transform through marginal CDFs via probability integral transform
    u = stats.norm.cdf(z)

    # Invert each marginal
    samples = np.zeros((n, k))
    for i, spec in enumerate(specs):
        dist = make_scipy_dist(spec)
        samples[:, i] = dist.ppf(u[:, i])
        if spec.bounds is not None:
            lo, hi = spec.bounds
            samples[:, i] = np.clip(samples[:, i], lo, hi)

    return samples


def inverse_cdf_from_unit(spec: UncertaintySpec, u: np.ndarray) -> np.ndarray:
    """Map uniform samples in (0, 1) through the inverse CDF of ``spec``.

    Used so Sobol'/LHS coverage is preserved across the marginal transform.
    """
    dist = make_scipy_dist(spec)
    # Clip strictly inside (0, 1) so ppf doesn't blow up at the edges.
    u_clipped = np.clip(u, 1e-12, 1 - 1e-12)
    samples = np.asarray(dist.ppf(u_clipped), dtype=np.float64)
    if spec.bounds is not None:
        lo, hi = spec.bounds
        samples = np.clip(samples, lo, hi)
    return samples
