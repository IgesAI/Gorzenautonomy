"""Dryden / Von Karman length scales use MIL-F-8785 altitude in feet, converted to metres."""

from __future__ import annotations

import math

from gorzen.models.environment import DrydenTurbulence, VonKarmanTurbulence, _M_PER_FT, _altitude_ft


def test_altitude_ft_conversion() -> None:
    assert abs(_altitude_ft(304.8) - 1000.0) < 0.5


def test_dryden_lu_matches_ft_formula() -> None:
    altitude_m = 304.8  # ~1000 ft
    h_ft = _altitude_ft(altitude_m)
    expected_lu_ft = h_ft / (0.177 + 0.000823 * h_ft) ** 1.2
    expected_lu_m = expected_lu_ft * _M_PER_FT
    d = DrydenTurbulence(wind_speed_6m=5.0, altitude_m=altitude_m)
    assert math.isclose(d.Lu, expected_lu_m, rel_tol=1e-9)


def test_von_karman_lu_matches_ft_formula() -> None:
    altitude_m = 152.4  # ~500 ft
    h_ft = _altitude_ft(altitude_m)
    expected_lu_ft = h_ft / (0.177 + 0.000823 * h_ft) ** 1.2
    vk = VonKarmanTurbulence(wind_speed_6m=5.0, altitude_m=altitude_m)
    assert math.isclose(vk.Lu, expected_lu_ft * _M_PER_FT, rel_tol=1e-9)
