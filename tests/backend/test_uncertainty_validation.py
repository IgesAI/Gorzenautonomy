"""Uncertainty modeling validation.

Monte Carlo propagation and sensitivity sanity checks.
"""

from __future__ import annotations

import numpy as np
import pytest

from gorzen.schemas.parameter import DistributionType, UncertaintySpec
from gorzen.schemas.twin_graph import VehicleTwin
from gorzen.solver.envelope_solver import compute_envelope
from gorzen.uq.monte_carlo import MCInput, MonteCarloEngine
from gorzen.uq.propagation import UQPropagator


class TestMCPropagation:
    """Monte Carlo produces sensible results."""

    def test_mc_increases_std_with_input_uncertainty(self):
        """Higher input std → higher output std."""
        def model(x: dict) -> dict:
            return {"y": x["a"] + x["b"]}

        engine = MonteCarloEngine(n_samples=500, seed=42)
        low_std = engine.propagate(
            model,
            [
                MCInput("a", 1.0, UncertaintySpec(distribution=DistributionType.NORMAL, params={"mean": 1.0, "std": 0.1})),
                MCInput("b", 2.0, UncertaintySpec(distribution=DistributionType.NORMAL, params={"mean": 2.0, "std": 0.1})),
            ],
        )
        high_std = engine.propagate(
            model,
            [
                MCInput("a", 1.0, UncertaintySpec(distribution=DistributionType.NORMAL, params={"mean": 1.0, "std": 0.5})),
                MCInput("b", 2.0, UncertaintySpec(distribution=DistributionType.NORMAL, params={"mean": 2.0, "std": 0.5})),
            ],
        )
        assert np.std(high_std.output_samples["y"]) > np.std(low_std.output_samples["y"])

    def test_mcp_in_valid_range(self):
        """MCP is always in [0, 1]."""
        twin = VehicleTwin()
        resp = compute_envelope(twin, grid_resolution=5, mc_samples=200)
        assert 0.0 <= resp.mission_completion_probability <= 1.0

    def test_sensitivity_ranking_non_empty(self):
        """Sensitivity produces ranking when constraints exist."""
        twin = VehicleTwin()
        resp = compute_envelope(twin, grid_resolution=5, mc_samples=200)
        assert len(resp.sensitivity) > 0
        # Top contributor should have positive correlation
        assert resp.sensitivity[0].contribution_pct >= 0
