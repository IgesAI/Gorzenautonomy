"""UQ surfaces model evaluation failures (MC / UT / PCE)."""

from __future__ import annotations

import numpy as np
import pytest

from gorzen.schemas.parameter import DistributionType, UncertaintySpec

_U01 = UncertaintySpec(
    distribution=DistributionType.UNIFORM,
    params={"low": 0.0, "high": 1.0},
    bounds=(0.0, 1.0),
)
from gorzen.uq.monte_carlo import MCInput, MonteCarloEngine
from gorzen.uq.propagation import UQInput, UQPropagator
from gorzen.uq.unscented import UnscentedTransform


def test_mc_result_counts_failures() -> None:
    def flaky(inp: dict[str, float]) -> dict[str, float]:
        if inp["x"] > 0.5:
            raise RuntimeError("fail")
        return {"y": inp["x"]}

    engine = MonteCarloEngine(n_samples=20, seed=0)
    res = engine.propagate(
        flaky,
        [MCInput("x", 0.5, _U01)],
    )
    assert res.n_attempted == 20
    assert res.n_failed >= 1
    assert res.n_samples + res.n_failed == res.n_attempted


def test_uq_propagator_mc_warning_on_failures() -> None:
    def flaky(inp: dict[str, float]) -> dict[str, float]:
        if inp["x"] < 0.2:
            raise RuntimeError("fail")
        return {"y": 1.0}

    uq = UQPropagator(method="monte_carlo", mc_samples=30, seed=0)
    result = uq.propagate(
        flaky,
        [UQInput("x", 0.5, uncertainty=_U01)],
        output_names=["y"],
    )
    assert result.raw_mc is not None
    assert result.raw_mc.n_failed > 0
    assert any("Monte Carlo" in w for w in result.warnings)


def test_ut_records_sigma_point_failures() -> None:
    """First model evaluation fails; nominal fallback succeeds — failure is counted."""

    class _CountingModel:
        __slots__ = ("n",)

        def __init__(self) -> None:
            self.n = 0

        def __call__(self, inp: dict[str, float]) -> dict[str, float]:
            self.n += 1
            if self.n == 1:
                raise RuntimeError("deliberate first-call failure")
            return {"y": 1.0}

    ut = UnscentedTransform()
    res = ut.propagate(
        _CountingModel(),
        ["x", "y"],
        np.array([1.0, 1.0]),
        np.diag([0.25, 0.25]),
    )
    assert res.sigma_point_evaluation_failures >= 1
    assert len(res.warnings) >= 1
