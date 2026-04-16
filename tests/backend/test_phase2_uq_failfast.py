"""Phase 2a regression tests — UQ fail-fast and QMC sampling."""

from __future__ import annotations

import numpy as np
import pytest

from gorzen.schemas.parameter import DistributionType, UncertaintySpec
from gorzen.uq.distributions import (
    inverse_cdf_from_unit,
    make_scipy_dist,
    sample_correlated,
)
from gorzen.uq.errors import (
    InvalidCorrelationError,
    MissingOutputError,
    MissingUncertaintyError,
    ModelEvaluationError,
    UnknownMethodError,
)
from gorzen.uq.monte_carlo import MCInput, MCResult, MonteCarloEngine
from gorzen.uq.pce import PCESurrogate
from gorzen.uq.propagation import UQInput, UQPropagator
from gorzen.uq.unscented import UnscentedTransform


class TestDistributionsRequireParams:
    def test_normal_missing_std_raises(self) -> None:
        spec = UncertaintySpec(distribution=DistributionType.NORMAL, params={"mean": 1.0})
        with pytest.raises(MissingUncertaintyError):
            make_scipy_dist(spec)

    def test_uniform_high_not_greater_than_low_raises(self) -> None:
        spec = UncertaintySpec(
            distribution=DistributionType.UNIFORM, params={"low": 1.0, "high": 1.0}
        )
        with pytest.raises(MissingUncertaintyError):
            make_scipy_dist(spec)

    def test_triangular_requires_bounds(self) -> None:
        spec = UncertaintySpec(
            distribution=DistributionType.TRIANGULAR,
            params={"low": 5.0, "mode": 3.0, "high": 4.0},
        )
        with pytest.raises(MissingUncertaintyError):
            make_scipy_dist(spec)


class TestCorrelationPsd:
    def test_non_psd_raises(self) -> None:
        specs = [
            UncertaintySpec(distribution=DistributionType.NORMAL, params={"mean": 0.0, "std": 1.0})
            for _ in range(2)
        ]
        # Off-diagonals > 1 make the matrix non-PSD.
        corr = np.array([[1.0, 1.5], [1.5, 1.0]])
        with pytest.raises(InvalidCorrelationError):
            sample_correlated(specs, corr, n=10)

    def test_non_symmetric_raises(self) -> None:
        specs = [
            UncertaintySpec(distribution=DistributionType.NORMAL, params={"mean": 0.0, "std": 1.0})
            for _ in range(2)
        ]
        corr = np.array([[1.0, 0.2], [0.3, 1.0]])
        with pytest.raises(InvalidCorrelationError):
            sample_correlated(specs, corr, n=10)

    def test_valid_correlation_samples(self) -> None:
        specs = [
            UncertaintySpec(distribution=DistributionType.NORMAL, params={"mean": 0.0, "std": 1.0})
            for _ in range(2)
        ]
        corr = np.array([[1.0, 0.5], [0.5, 1.0]])
        samples = sample_correlated(specs, corr, n=500, rng=np.random.default_rng(1))
        observed = float(np.corrcoef(samples[:, 0], samples[:, 1])[0, 1])
        assert 0.3 < observed < 0.7


class TestMcMissingOutputFailsFast:
    def test_envelope_missing_raises(self) -> None:
        result = MCResult(output_samples={"y": np.array([1.0, 2.0, 3.0])})
        with pytest.raises(MissingOutputError):
            result.envelope_output("z")

    def test_probability_missing_raises(self) -> None:
        result = MCResult(output_samples={"y": np.array([1.0, 2.0, 3.0])})
        with pytest.raises(MissingOutputError):
            result.probability_constraint_satisfied("z", 0.5)

    def test_strict_mode_raises_on_first_failure(self) -> None:
        def bad_model(_: dict[str, float]) -> dict[str, float]:
            raise RuntimeError("boom")

        engine = MonteCarloEngine(n_samples=4, seed=0, sampling="lhs", strict_model=True)
        with pytest.raises(ModelEvaluationError):
            engine.propagate(bad_model, [MCInput(name="x", nominal=0.0)])


class TestQmcSampling:
    def test_sobol_preserves_coverage(self) -> None:
        engine = MonteCarloEngine(n_samples=64, seed=0, sampling="sobol")
        samples = engine._unit_samples(2)
        # Sobol' covers the unit cube better than IID; assert each quadrant has >=10 points.
        quadrants = [
            ((samples[:, 0] < 0.5) & (samples[:, 1] < 0.5)).sum(),
            ((samples[:, 0] < 0.5) & (samples[:, 1] >= 0.5)).sum(),
            ((samples[:, 0] >= 0.5) & (samples[:, 1] < 0.5)).sum(),
            ((samples[:, 0] >= 0.5) & (samples[:, 1] >= 0.5)).sum(),
        ]
        for q in quadrants:
            assert q >= 10

    def test_lhs_preserves_stratification(self) -> None:
        engine = MonteCarloEngine(n_samples=50, seed=0, sampling="lhs")
        samples = engine._unit_samples(1)
        # LHS guarantees one sample per stratum of width 1/n.
        bucket = np.floor(samples[:, 0] * 50).astype(int)
        assert len(set(bucket)) == 50

    def test_inverse_cdf_from_unit_maps_to_bounds(self) -> None:
        spec = UncertaintySpec(
            distribution=DistributionType.UNIFORM, params={"low": 10.0, "high": 20.0}
        )
        u = np.linspace(0.05, 0.95, 10)
        phys = inverse_cdf_from_unit(spec, u)
        assert phys.min() >= 10.0
        assert phys.max() <= 20.0


class TestUtRequiresUncertainty:
    def test_missing_std_raises(self) -> None:
        prop = UQPropagator(method="unscented")
        # Uncertainty present but has no 'std' and no bounds.
        inp = UQInput(
            name="x",
            nominal=1.0,
            uncertainty=UncertaintySpec(distribution=DistributionType.NORMAL, params={"mean": 1.0}),
        )
        with pytest.raises(MissingUncertaintyError):
            # make_scipy_dist also raises; catch both — covered in distributions tests.
            prop.propagate(lambda x: {"y": x["x"]}, [inp])


class TestUnknownMethodRaises:
    def test_unknown_method(self) -> None:
        prop = UQPropagator(method="bogus")
        with pytest.raises(UnknownMethodError):
            prop.propagate(lambda x: {"y": 1.0}, [])


class TestPceFailFast:
    def test_pce_strict_raises_on_failure(self) -> None:
        def bad_model(_: dict[str, float]) -> dict[str, float]:
            raise RuntimeError("pce boom")

        pce = PCESurrogate(max_order=2, strict_model=True)
        with pytest.raises(ModelEvaluationError):
            pce.fit(bad_model, ["x"], [(0.0, 1.0)])


class TestUtStrict:
    def test_ut_strict_raises_on_bad_cov(self) -> None:
        ut = UnscentedTransform()
        # Negative definite -> Cholesky fails -> InvalidCorrelationError (no silent jitter).
        with pytest.raises(InvalidCorrelationError):
            ut.propagate(
                lambda x: {"y": 1.0},
                ["x"],
                np.array([1.0]),
                np.array([[-1.0]]),
            )

    def test_ut_strict_raises_on_model_failure(self) -> None:
        def bad(_: dict[str, float]) -> dict[str, float]:
            raise RuntimeError("no good")

        ut = UnscentedTransform()
        with pytest.raises(ModelEvaluationError):
            ut.propagate(bad, ["x"], np.array([1.0]), np.array([[0.25]]))
