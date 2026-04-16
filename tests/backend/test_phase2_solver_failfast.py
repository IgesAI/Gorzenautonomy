"""Phase 2b regression tests — solver/models fail-fast contracts."""

from __future__ import annotations

import pytest

from gorzen.models.airframe import AirframeModel
from gorzen.models.base import ModelOutput, MissingModelOutputError
from gorzen.models.comms import CommsModel
from gorzen.models.perception.image_quality import ImageQualityModel
from gorzen.models.propulsion import RotorModel
from gorzen.schemas.twin_graph import VehicleTwin
from gorzen.solver.envelope_solver import _extract_params, evaluate_point
from gorzen.solver.errors import MissingSolverParamError


class TestModelOutputRequire:
    def test_require_raises_on_missing(self) -> None:
        out = ModelOutput(values={"a": 1.0})
        with pytest.raises(MissingModelOutputError):
            out.require("b")

    def test_getitem_raises_on_missing(self) -> None:
        out = ModelOutput(values={"a": 1.0})
        with pytest.raises(MissingModelOutputError):
            _ = out["b"]


class TestAirframeRequiresAoa:
    def test_missing_alpha_rad_raises(self) -> None:
        twin = VehicleTwin()
        params = _extract_params(twin)
        conditions = {"airspeed_ms": 20.0, "altitude_m": 100.0, "temperature_c": 20.0}
        model = AirframeModel()
        with pytest.raises(ValueError):  # require_param raises ValueError
            model.evaluate(params, conditions)


class TestCommsParamNames:
    def test_encoding_bitrate_is_declared(self) -> None:
        assert "encoding_bitrate_mbps" in CommsModel().parameter_names()

    def test_no_bandwidth_makes_link_infeasible(self) -> None:
        twin = VehicleTwin()
        params = _extract_params(twin)
        # Force out-of-range and no satcom
        params["satcom_available"] = 0.0
        params["encoding_bitrate_mbps"] = 5.0
        conditions = {
            "distance_to_gcs_km": 1_000.0,  # beyond MANET range
            "manet_frequency_mhz": 1350.0,
        }
        out = CommsModel().evaluate(params, conditions)
        assert out.values["achievable_bitrate_mbps"] == pytest.approx(0.0)
        assert out.values["link_feasible"] == pytest.approx(0.0)


class TestRotorRpmMax:
    def test_rotor_rpm_max_is_declared(self) -> None:
        assert "rotor_rpm_max" in RotorModel().parameter_names()


class TestGiqeH:
    def test_h_term_applied_when_sharpening_gain_greater_than_one(self) -> None:
        twin = VehicleTwin()
        params = _extract_params(twin)
        conditions = {
            "gsd_cm_px": 2.0,
            "smear_pixels": 0.1,
            "ambient_light_lux_out": 10_000.0,
            "compression_quality_factor": 90.0,
        }
        out_no_sharp = ImageQualityModel().evaluate(params, conditions)
        params_sharp = dict(params)
        params_sharp["post_processing_sharpening_gain"] = 3.0
        out_sharp = ImageQualityModel().evaluate(params_sharp, conditions)
        # Sharpening increases G/SNR penalty (C3) and edge overshoot (C4, negative),
        # both reducing NIIRS versus the no-sharpening baseline.
        assert out_sharp.values["niirs_equivalent"] < out_no_sharp.values["niirs_equivalent"]


class TestEnvelopeFailFast:
    def test_missing_critical_param_raises_at_evaluate(self) -> None:
        params = {"wing_span_m": 5.0}  # nowhere near complete
        with pytest.raises(MissingSolverParamError):
            evaluate_point(params, 15.0, 100.0)
