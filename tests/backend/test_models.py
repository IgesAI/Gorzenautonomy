"""Unit tests for physics and perception models."""

from __future__ import annotations

import numpy as np
import pytest

from gorzen.models.battery import BatteryModel, lipo_ocv
from gorzen.models.comms import CommsModel
from gorzen.models.environment import EnvironmentModel
from gorzen.models.perception.gsd import GSDModel
from gorzen.models.perception.motion_blur import MotionBlurModel
from gorzen.models.propulsion import RotorModel


class TestLipoOcv:
    """LiPo OCV curve: 3.0V @ 0%, 4.2V @ 100%."""

    def test_soc_zero(self):
        assert abs(lipo_ocv(0.0) - 3.0) < 0.01

    def test_soc_full(self):
        assert abs(lipo_ocv(1.0) - 4.2) < 0.01

    def test_soc_clipped(self):
        assert lipo_ocv(-0.1) >= 3.0
        assert lipo_ocv(1.5) <= 4.2


class TestEnvironmentModel:
    """ISA density, temperature offset."""

    def test_air_density_sea_level(self):
        m = EnvironmentModel()
        out = m.evaluate(
            {"pressure_hpa": 1013.25, "temperature_c": 15.0},
            {"altitude_m": 0.0, "heading_deg": 0.0},
        )
        rho = out.values["air_density_kgm3"]
        assert 1.2 < rho < 1.25

    def test_wind_components(self):
        m = EnvironmentModel()
        out = m.evaluate(
            {"wind_speed_ms": 10.0, "wind_direction_deg": 0.0},
            {"altitude_m": 50.0, "heading_deg": 0.0},
        )
        assert abs(out.values["headwind_ms"] - 10.0) < 0.01
        assert abs(out.values["crosswind_ms"]) < 0.01


class TestCommsModel:
    """FSPL = 20*log10(d) + 20*log10(f) + 32.45."""

    def test_fspl_increases_with_distance(self):
        m = CommsModel()
        out1 = m.evaluate({}, {"distance_to_gcs_km": 1.0})
        out2 = m.evaluate({}, {"distance_to_gcs_km": 10.0})
        assert out2.values["link_margin_db"] < out1.values["link_margin_db"]


class TestGSDModel:
    """GSD = (sensor_width * altitude) / (focal_length * pixel_width)."""

    def test_gsd_scales_with_altitude(self):
        m = GSDModel()
        out_low = m.evaluate(
            {"sensor_width_mm": 13.2, "focal_length_mm": 24.0, "pixel_width": 4000},
            {"altitude_m": 50.0},
        )
        out_high = m.evaluate(
            {"sensor_width_mm": 13.2, "focal_length_mm": 24.0, "pixel_width": 4000},
            {"altitude_m": 100.0},
        )
        assert out_high.values["gsd_cm_px"] > out_low.values["gsd_cm_px"]

    def test_pixels_on_target(self):
        m = GSDModel()
        out = m.evaluate(
            {"sensor_width_mm": 13.2, "focal_length_mm": 24.0, "pixel_width": 4000},
            {"altitude_m": 50.0, "target_size_m": 1.0},
        )
        pot = out.values["pixels_on_target"]
        assert pot > 0
        assert np.isfinite(pot)


class TestMotionBlurModel:
    """smear_pixels = (v * t_exposure) / GSD."""

    def test_smear_increases_with_speed(self):
        m = MotionBlurModel()
        out_slow = m.evaluate(
            {"exposure_time_s": 1.0 / 2000.0},
            {"airspeed_ms": 5.0, "gsd_cm_px": 1.0, "max_blur_px": 2.0},
        )
        out_fast = m.evaluate(
            {"exposure_time_s": 1.0 / 2000.0},
            {"airspeed_ms": 20.0, "gsd_cm_px": 1.0, "max_blur_px": 2.0},
        )
        assert out_fast.values["smear_pixels"] > out_slow.values["smear_pixels"]


class TestRotorModel:
    """T = CT * rho * n^2 * D^4."""

    def test_thrust_with_density(self):
        m = RotorModel()
        out_low = m.evaluate(
            {"rotor_count": 4, "rotor_diameter_m": 0.6, "prop_ct_static": 0.1},
            {"altitude_m": 0.0, "rotor_lift_required_N": 500.0, "airspeed_ms": 0.0},
        )
        out_high = m.evaluate(
            {"rotor_count": 4, "rotor_diameter_m": 0.6, "prop_ct_static": 0.1},
            {"altitude_m": 3000.0, "rotor_lift_required_N": 500.0, "airspeed_ms": 0.0},
        )
        assert out_high.values["rotor_power_total_W"] > out_low.values["rotor_power_total_W"]


class TestBatteryModel:
    """Endurance from usable energy / power draw."""

    def test_endurance_decreases_with_load(self):
        m = BatteryModel()
        out_light = m.evaluate(
            {"cell_count_s": 6, "capacity_ah": 10.0, "soh_pct": 100.0},
            {"soc": 0.8, "total_electrical_power_W": 100.0},
        )
        out_heavy = m.evaluate(
            {"cell_count_s": 6, "capacity_ah": 10.0, "soh_pct": 100.0},
            {"soc": 0.8, "total_electrical_power_W": 400.0},
        )
        assert out_heavy.values["endurance_min"] < out_light.values["endurance_min"]
