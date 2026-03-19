"""Data sources for physics validation and calibration.

Phase 2: Integrate real data sources:
- UIUC Prop Database (propeller thrust/power)
- NASA airfoil data (if needed)
- LiPo discharge curves (OCV vs SOC)
"""

from gorzen.data.lipo import get_lipo_ocv_curve, interpolate_ocv
from gorzen.data.uiuc_prop import get_prop_coefficients

__all__ = ["get_lipo_ocv_curve", "interpolate_ocv", "get_prop_coefficients"]
