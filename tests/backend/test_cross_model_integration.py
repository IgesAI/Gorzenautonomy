"""Cross-model integration tests.

Validates that constraint failures propagate correctly through the full pipeline.
Example: motion_blur fails → envelope must be infeasible (not "valid").
"""

from __future__ import annotations

import pytest

from gorzen.schemas.twin_graph import VehicleTwin
from gorzen.solver.envelope_solver import _extract_params, evaluate_point, compute_envelope


class TestConstraintFailurePropagation:
    """When a constraint fails, envelope must reflect it."""

    def test_motion_blur_failure_makes_envelope_infeasible(self):
        """High speed + strict max_blur → motion blur fails → envelope infeasible."""
        twin = VehicleTwin()
        # Strict blur limit: 0.2 px (exposure is 1/2000 s in solver)
        # At 30 m/s: smear = 30*0.0005 = 0.015 m. GSD ~2cm → smear_px ~0.75 > 0.2
        twin.mission_profile.constraints.max_blur_px.value = 0.2
        params = _extract_params(twin)

        out = evaluate_point(params, 30.0, 100.0)
        blur_ok = out.get("motion_blur_feasible", 1.0) > 0.5
        assert not blur_ok, "Motion blur should fail at 30 m/s with max_blur=0.2"

        # Envelope at high-speed point must be infeasible
        resp = compute_envelope(twin, grid_resolution=10)
        # Find high-speed point in grid
        for i, alt in enumerate(resp.speed_altitude_feasibility.y_values):
            for j, spd in enumerate(resp.speed_altitude_feasibility.x_values):
                if spd >= 28 and 95 <= alt <= 105:
                    feasible = resp.speed_altitude_feasibility.feasible_mask[i][j]
                    assert not feasible, f"Envelope must be infeasible at ({spd}, {alt}) when motion blur fails"
                    return

    def test_identification_degraded_when_blur_exceeds_limit(self):
        """When smear_pixels is high, identification_confidence must drop."""
        twin = VehicleTwin()
        params = _extract_params(twin)

        # Low speed: blur OK
        out_slow = evaluate_point(params, 5.0, 50.0)
        ident_slow = out_slow.get("identification_confidence", 0.0)

        # High speed: blur worse
        out_fast = evaluate_point(params, 25.0, 50.0)
        ident_fast = out_fast.get("identification_confidence", 0.0)

        assert ident_fast < ident_slow, "Higher speed → more blur → lower identification confidence"

    def test_gsd_and_blur_consistent(self):
        """GSD and motion blur use same inputs; both feed identification."""
        twin = VehicleTwin()
        params = _extract_params(twin)

        # At 50m: better GSD than 150m
        out_low = evaluate_point(params, 15.0, 50.0)
        out_high = evaluate_point(params, 15.0, 150.0)

        gsd_low = out_low.get("gsd_cm_px", 999.0)
        gsd_high = out_high.get("gsd_cm_px", 0.0)
        assert gsd_low < gsd_high

        ident_low = out_low.get("identification_confidence", 0.0)
        ident_high = out_high.get("identification_confidence", 0.0)
        assert ident_low > ident_high, "Better GSD → higher identification confidence"
