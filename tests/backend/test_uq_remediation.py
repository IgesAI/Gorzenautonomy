"""UQ conservative behavior: MC failure-rate MCP, UT weight renormalization."""

from __future__ import annotations

import numpy as np

from gorzen.uq.propagation import UQInput, UQPropagator
from gorzen.uq.unscented import UnscentedTransform


def test_mc_high_failure_rate_zeros_mcp() -> None:
    """>5% model failures forces mission_completion_probability to 0 when constraints are set."""
    calls = {"n": 0}

    def model_fn(inp: dict[str, float]) -> dict[str, float]:
        calls["n"] += 1
        if calls["n"] <= 10:
            raise RuntimeError("fail")
        return {"y": 1.0}

    prop = UQPropagator(method="monte_carlo", mc_samples=40, seed=1)
    result = prop.propagate(
        model_fn,
        [UQInput(name="x", nominal=1.0)],
        output_names=["y"],
        constraints={"y": (0.5, ">=")},
    )
    assert result.mission_completion_probability == 0.0
    assert any("failure rate" in w.lower() for w in result.warnings)


def test_ut_partial_failure_reweights() -> None:
    """Sigma points away from nominal can fail; remaining points are reweighted."""

    def model_fn(inp: dict[str, float]) -> dict[str, float]:
        # Only the central sigma (index 0) should match mean exactly in float space
        if inp["x"] != 1.0:
            raise RuntimeError("fail_off_nominal")
        return {"y": 1.0}

    # Exercise the degraded "drop + reweight" path explicitly — strict=True
    # would (correctly) refuse to produce UT statistics from a subset of sigma
    # points, so we opt into the lossy behaviour for this test.
    ut = UnscentedTransform(strict_model=False)
    res = ut.propagate(model_fn, ["x"], np.array([1.0]), np.array([[0.25]]))
    assert res.sigma_point_evaluation_failures >= 1
    assert "y" in res.output_mean
    assert np.isfinite(res.output_std.get("y", float("nan")))
