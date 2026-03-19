"""Unit handling with pint (Phase 5/6).

Use for validation and conversion. Example:
    from gorzen.units import ureg
    v_ms = (15 * ureg.knot).to(ureg.m / ureg.s)
"""

from __future__ import annotations

try:
    import pint

    ureg = pint.UnitRegistry()
    Q_ = ureg.Quantity
    HAS_PINT = True
except ImportError:
    ureg = None
    Q_ = None
    HAS_PINT = False


def convert_speed(value: float, from_unit: str, to_unit: str = "m/s") -> float:
    """Convert speed between units. Fallback if pint not installed."""
    if not HAS_PINT:
        # Minimal conversions without pint
        from_lower = from_unit.lower()
        if "knot" in from_lower or "kt" in from_lower:
            return value * 0.514444  # knots to m/s
        if "mph" in from_lower:
            return value * 0.44704
        return value
    q = Q_(value, from_unit)
    return q.to(to_unit).magnitude
