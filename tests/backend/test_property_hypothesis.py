"""Property-based tests with Hypothesis (Phase 5/6).

Validates invariants across random inputs.
"""

from __future__ import annotations

import numpy as np
from hypothesis import given, strategies as st

from gorzen.models.battery import lipo_ocv
from gorzen.models.perception.gsd import GSDModel


class TestLiPoOCVProperties:
    """Property-based tests for LiPo OCV curve."""

    @given(st.floats(min_value=0.0, max_value=1.0))
    def test_ocv_in_valid_range(self, soc: float) -> None:
        """OCV always in [3.0, 4.2] for 0 <= soc <= 1."""
        v = lipo_ocv(soc)
        assert 3.0 <= v <= 4.2

    @given(st.floats(min_value=0.0, max_value=1.0))
    def test_ocv_monotonic(self, soc: float) -> None:
        """OCV increases with SOC."""
        v1 = lipo_ocv(soc)
        v2 = lipo_ocv(min(soc + 0.01, 1.0))
        assert v2 >= v1 - 0.01  # allow small numerical error


class TestGSDProperties:
    """Property-based tests for GSD model."""

    @given(
        alt=st.floats(min_value=10.0, max_value=500.0),
        sw=st.floats(min_value=5.0, max_value=25.0),
        fl=st.floats(min_value=10.0, max_value=50.0),
        px=st.integers(min_value=1000, max_value=8000),
    )
    def test_gsd_positive_and_finite(self, alt: float, sw: float, fl: float, px: int) -> None:
        """GSD is positive and finite for valid inputs."""
        m = GSDModel()
        out = m.evaluate(
            {"sensor_width_mm": sw, "focal_length_mm": fl, "pixel_width": px, "sensor_height_mm": sw * 0.67, "pixel_height": int(px * 0.75)},
            {"altitude_m": alt},
        )
        gsd = out.values["gsd_cm_px"]
        assert gsd > 0
        assert np.isfinite(gsd)
