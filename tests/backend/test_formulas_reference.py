"""Phase 1: Formula validation against physical references.

Validates:
1. Rotor thrust (momentum theory: T = 2*rho*A*v_i^2)
2. Drag (D = 0.5*rho*v^2*Cd*A)
3. GSD (GSD = sensor_width*altitude / (focal_length*image_width))
4. Motion blur (max_velocity = blur_pixels*GSD / exposure_time)
"""

from __future__ import annotations

import numpy as np
import pytest

from gorzen.models.airframe import AirframeModel
from gorzen.models.perception.gsd import GSDModel
from gorzen.models.perception.motion_blur import MotionBlurModel, compute_required_shutter_speed
from gorzen.models.propulsion import RotorModel, isa_density


# ---------------------------------------------------------------------------
# 1. Rotor thrust: momentum theory T = 2*rho*A*v_i^2 => v_i = sqrt(T/(2*rho*A))
#    CT formulation: T = CT*rho*n^2*D^4 => n = sqrt(T/(CT*rho*D^4))
#    For hover, both should give consistent power: P_ideal = T*v_i (momentum)
# ---------------------------------------------------------------------------
class TestRotorMomentumTheory:
    """Cross-check rotor model against momentum theory."""

    def test_thrust_from_ct_matches_disk_area(self):
        """T = CT*rho*n^2*D^4; for given T, induced velocity v_i = sqrt(T/(2*rho*A))."""
        rho = 1.225
        D = 0.6
        A = np.pi * (D / 2) ** 2
        T = 500.0  # N total for 4 rotors
        T_per = T / 4.0

        # Momentum theory: v_i = sqrt(T/(2*rho*A))
        v_i = np.sqrt(T_per / (2 * rho * A))
        assert v_i > 0
        assert 5 < v_i < 25  # typical range for small VTOL

    def test_rotor_model_produces_expected_thrust(self):
        """RotorModel with known inputs produces thrust consistent with CT formula."""
        m = RotorModel()
        rho = 1.225
        D = 0.6
        ct0 = 0.1
        n_rotors = 4
        n_rps = 50.0  # 3000 rpm

        # T = CT*rho*n^2*D^4 per rotor
        T_expected = ct0 * rho * n_rps**2 * D**4 * n_rotors

        out = m.evaluate(
            {"rotor_count": n_rotors, "rotor_diameter_m": D, "prop_ct_static": ct0},
            {
                "altitude_m": 0.0,
                "rotor_lift_required_N": T_expected,
                "airspeed_ms": 0.0,
                "air_density_kgm3": rho,
            },
        )
        T_actual = out.values["rotor_thrust_total_N"]
        assert abs(T_actual - T_expected) / (T_expected + 1e-6) < 0.05


# ---------------------------------------------------------------------------
# 2. Drag: D = 0.5*rho*v^2*Cd*A (Cd = cd0 + Cdi)
# ---------------------------------------------------------------------------
class TestDragModel:
    """D = 0.5*rho*v^2*Cd*A."""

    def test_drag_formula(self):
        """Verify D = q*S*Cd where q = 0.5*rho*v^2."""
        rho = 1.225
        v = 20.0
        S = 1.2
        cd0 = 0.03
        # Simplified: no induced drag (high speed or CL=0)
        Cd = cd0
        q = 0.5 * rho * v**2
        D_expected = q * S * Cd

        m = AirframeModel()
        out = m.evaluate(
            {"wing_area_m2": S, "cd0": cd0, "wing_span_m": 2.0, "oswald_efficiency": 0.8},
            {"airspeed_ms": v, "altitude_m": 0.0, "alpha_rad": 0.0, "air_density_kgm3": rho},
        )
        D_actual = out.values["drag_N"]
        assert abs(D_actual - D_expected) / (D_expected + 1e-6) < 0.02


# ---------------------------------------------------------------------------
# 3. GSD = (sensor_width * altitude) / (focal_length * image_width)
# ---------------------------------------------------------------------------
class TestGSDFormula:
    """GSD = (sensor_width * altitude) / (focal_length * image_width)."""

    def test_gsd_formula(self):
        """Reference: GSD [m/px] = (sensor_width_mm * alt_m) / (focal_length_mm * pixel_width)."""
        sw_mm = 13.2
        fl_mm = 24.0
        px_w = 4000
        alt_m = 100.0

        gsd_expected_m = (sw_mm * alt_m) / (fl_mm * px_w)
        gsd_expected_cm = gsd_expected_m * 100.0

        m = GSDModel()
        out = m.evaluate(
            {"sensor_width_mm": sw_mm, "focal_length_mm": fl_mm, "pixel_width": px_w},
            {"altitude_m": alt_m},
        )
        assert abs(out.values["gsd_w_cm_px"] - gsd_expected_cm) < 0.01

    def test_gsd_scales_linearly_with_altitude(self):
        """GSD ∝ altitude."""
        m = GSDModel()
        out1 = m.evaluate(
            {"sensor_width_mm": 13.2, "focal_length_mm": 24.0, "pixel_width": 4000},
            {"altitude_m": 50.0},
        )
        out2 = m.evaluate(
            {"sensor_width_mm": 13.2, "focal_length_mm": 24.0, "pixel_width": 4000},
            {"altitude_m": 100.0},
        )
        ratio = out2.values["gsd_cm_px"] / (out1.values["gsd_cm_px"] + 1e-9)
        assert 1.95 < ratio < 2.05


# ---------------------------------------------------------------------------
# 4. Motion blur: max_velocity = (blur_pixels * GSD) / exposure_time
# ---------------------------------------------------------------------------
class TestMotionBlurFormula:
    """max_velocity = (blur_pixels * GSD) / exposure_time."""

    def test_safe_speed_formula(self):
        """max_v = blur_budget * GSD / t_exposure."""
        gsd_cm = 2.0  # 2 cm/px
        gsd_m = gsd_cm / 100.0
        t_exp = 1.0 / 2000.0  # 1/2000 s
        blur_budget = 0.5  # px

        max_v_expected = blur_budget * gsd_m / t_exp

        m = MotionBlurModel()
        out = m.evaluate(
            {"exposure_time_s": t_exp, "vibration_blur_px": 0.0},
            {"airspeed_ms": 1.0, "gsd_cm_px": gsd_cm, "max_blur_px": blur_budget},
        )
        assert abs(out.values["safe_inspection_speed_ms"] - max_v_expected) < 0.1

    def test_compute_required_shutter_speed(self):
        """Inverse: shutter_speed = 1/t where t = blur_budget*GSD/v."""
        v = 20.0
        gsd_cm = 1.0
        max_blur = 0.5
        shutter = compute_required_shutter_speed(v, gsd_cm, max_blur)
        assert shutter > 1000  # Should need fast shutter at 20 m/s
