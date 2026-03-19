"""LiPo discharge curve data for OCV vs SOC validation.

References:
- Typical LiPo: 3.0V @ 0%, 4.2V @ 100%
- Industry datasheets for specific cell chemistries
"""

from __future__ import annotations

import numpy as np


# Typical LiPo OCV curve (soc -> voltage) from reference data
# Points from common discharge curves
_LIPO_OCV_REFERENCE: list[tuple[float, float]] = [
    (0.00, 3.00),
    (0.05, 3.20),
    (0.10, 3.45),
    (0.20, 3.55),
    (0.30, 3.62),
    (0.40, 3.68),
    (0.50, 3.72),
    (0.60, 3.78),
    (0.70, 3.85),
    (0.80, 3.92),
    (0.90, 4.05),
    (0.95, 4.12),
    (1.00, 4.20),
]


def get_lipo_ocv_curve() -> np.ndarray:
    """Return reference OCV curve as (soc, voltage) array."""
    return np.array(_LIPO_OCV_REFERENCE)


def interpolate_ocv(soc: float) -> float:
    """Interpolate OCV at given SOC using reference curve."""
    curve = get_lipo_ocv_curve()
    return float(np.interp(np.clip(soc, 0.0, 1.0), curve[:, 0], curve[:, 1]))
