"""Distribution types, correlation groups, and evidence binding for UQ."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import stats

from gorzen.schemas.parameter import DistributionType, UncertaintySpec


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


def make_scipy_dist(spec: UncertaintySpec) -> stats.rv_continuous | stats.rv_discrete:
    """Convert an UncertaintySpec into a scipy distribution object."""
    p = spec.params
    dt = spec.distribution

    if dt == DistributionType.NORMAL:
        return stats.norm(loc=p.get("mean", 0), scale=p.get("std", 1))
    elif dt == DistributionType.UNIFORM:
        lo = p.get("low", 0)
        hi = p.get("high", 1)
        return stats.uniform(loc=lo, scale=hi - lo)
    elif dt == DistributionType.BETA:
        return stats.beta(a=p.get("a", 2), b=p.get("b", 5))
    elif dt == DistributionType.LOGNORMAL:
        mu = p.get("mu", 0)
        sigma = p.get("sigma", 0.5)
        return stats.lognorm(s=sigma, scale=np.exp(mu))
    elif dt == DistributionType.TRIANGULAR:
        lo = p.get("low", 0)
        mode = p.get("mode", 0.5)
        hi = p.get("high", 1)
        c = (mode - lo) / (hi - lo + 1e-12)
        return stats.triang(c=c, loc=lo, scale=hi - lo)
    elif dt == DistributionType.WEIBULL:
        return stats.weibull_min(c=p.get("shape", 2), scale=p.get("scale", 1))
    elif dt == DistributionType.EMPIRICAL:
        raise ValueError("Empirical distributions require sample data, not a parametric spec.")
    else:
        return stats.norm(loc=p.get("mean", 0), scale=p.get("std", 1))


def sample_from_spec(
    spec: UncertaintySpec,
    n: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Draw n samples from an UncertaintySpec. Uses fixed seed when rng is None for determinism."""
    if rng is None:
        rng = np.random.default_rng(42)

    dist = make_scipy_dist(spec)
    samples = dist.rvs(size=n, random_state=rng.integers(0, 2**31))

    if spec.bounds is not None:
        lo, hi = spec.bounds
        samples = np.clip(samples, lo, hi)

    return samples


def sample_correlated(
    specs: list[UncertaintySpec],
    correlation_matrix: np.ndarray,
    n: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Draw correlated samples from multiple specs using Gaussian copula.

    Returns shape (n, len(specs)). Uses fixed seed when rng is None for determinism.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    k = len(specs)
    assert correlation_matrix.shape == (k, k)

    # Generate correlated standard normals
    L = np.linalg.cholesky(correlation_matrix)
    z = rng.standard_normal((n, k)) @ L.T

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
