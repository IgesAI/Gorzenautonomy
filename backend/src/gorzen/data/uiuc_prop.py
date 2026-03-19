"""UIUC Propeller Database integration (Phase 2 stub).

UIUC Propeller Database: https://m-selig.ae.illinois.edu/props/volume-1/propDB.html

Provides CT, CP vs advance ratio for real propeller geometries.
To integrate: load CSV/JSON data, interpolate CT(μ), CP(μ).
"""

from __future__ import annotations

# Stub: actual integration would load UIUC prop data files
# and provide lookup(prop_id, mu) -> (CT, CP)


def get_prop_coefficients(prop_id: str, advance_ratio: float) -> tuple[float, float]:
    """Lookup CT, CP for a propeller at given advance ratio.

    Args:
        prop_id: Propeller identifier (e.g. 'APC_10x7')
        advance_ratio: μ = v / (n * D)

    Returns:
        (CT, CP) thrust and power coefficients
    """
    # Stub: return typical values until UIUC data is integrated
    del prop_id  # unused until integration
    # Typical: CT decreases with μ, CP increases slightly
    ct0 = 0.1
    cp0 = 0.04
    ct = ct0 * (1.0 - 0.3 * advance_ratio**2)
    cp = cp0 * (1.0 + 0.5 * advance_ratio**2)
    return (max(ct, 0.01), cp)
