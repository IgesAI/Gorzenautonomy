"""Tests for envelope solver and UQ propagation."""

from __future__ import annotations

import numpy as np

from gorzen.schemas.parameter import DistributionType, UncertaintySpec
from gorzen.schemas.twin_graph import VehicleTwin
from gorzen.solver.envelope_solver import _extract_params, compute_envelope, evaluate_point
from gorzen.uq.monte_carlo import MCInput, MonteCarloEngine


class TestEvaluatePoint:
    """Single-point model chain evaluation."""

    def test_returns_dict_with_expected_keys(self):
        twin = VehicleTwin()
        params = _extract_params(twin)
        out = evaluate_point(params, 15.0, 100.0)
        assert "identification_confidence" in out
        assert "fuel_endurance_hr" in out
        assert "battery_feasible" in out
        assert "aero_feasible" in out

    def test_identification_confidence_in_range(self):
        twin = VehicleTwin()
        params = _extract_params(twin)
        out = evaluate_point(params, 10.0, 50.0)
        ident = out.get("identification_confidence", 0.0)
        assert 0.0 <= ident <= 1.0


class TestComputeEnvelope:
    """Full envelope computation."""

    def test_returns_envelope_response(self):
        twin = VehicleTwin()
        resp = compute_envelope(twin, grid_resolution=5)
        assert resp.speed_altitude_feasibility is not None
        assert resp.identification_confidence is not None
        assert resp.mission_completion_probability is not None
        assert 0.0 <= resp.mission_completion_probability <= 1.0

    def test_surfaces_have_correct_shape(self):
        twin = VehicleTwin()
        resp = compute_envelope(twin, grid_resolution=6)
        surf = resp.speed_altitude_feasibility
        assert len(surf.x_values) == 6
        assert len(surf.y_values) == 6
        assert len(surf.z_mean) == 6
        assert len(surf.z_mean[0]) == 6


class TestMonteCarloEngine:
    """MC propagation and alignment."""

    def test_successful_runs_produce_aligned_samples(self):
        def model(x):
            return {"y": x["a"] + x["b"]}

        engine = MonteCarloEngine(n_samples=100, seed=42)
        result = engine.propagate(
            model,
            [
                MCInput("a", 1.0, UncertaintySpec(distribution=DistributionType.NORMAL, params={"mean": 1.0, "std": 0.1})),
                MCInput("b", 2.0, UncertaintySpec(distribution=DistributionType.NORMAL, params={"mean": 2.0, "std": 0.1})),
            ],
        )
        assert result.n_samples == 100
        assert "y" in result.output_samples
        assert len(result.output_samples["y"]) == 100
        assert len(result.input_samples["a"]) == 100
        assert np.allclose(result.output_samples["y"], result.input_samples["a"] + result.input_samples["b"])
