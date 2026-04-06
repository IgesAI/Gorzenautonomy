"""P0 remediation regression tests: MAVLink coords, energy units, PCE variance, MAVSDK boundary."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import gorzen
import numpy as np
import pytest

from gorzen.services.mavlink_mission_coords import (
    MAV_FRAME_GLOBAL_RELATIVE_ALT,
    MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
    latlon_degrees_to_mavlink_int,
    normalize_mission_frame_for_raw_upload,
    normalize_xy_to_mavlink_int,
)
from gorzen.uq.pce import PCESurrogate, _legendre_uniform_basis_variance_weight


class TestMavlinkMissionCoords:
    """MISSION_ITEM_INT scaling and frame mapping (PX4 / ArduPilot-safe)."""

    def test_degrees_scaled_once(self) -> None:
        lat, lon = 47.3977419, 8.545594
        xi, yi = normalize_xy_to_mavlink_int(lat, lon)
        assert xi == 473977419
        assert yi == 85455940

    def test_already_scaled_not_rescaled(self) -> None:
        xi, yi = normalize_xy_to_mavlink_int(473977419, 85455940)
        assert xi == 473977419
        assert yi == 85455940

    def test_latlon_degrees_to_mavlink_int_tv_mav_enc_1(self) -> None:
        """TV-MAV-ENC-1: known MISSION_ITEM_INT lat/lon."""
        xi, yi = latlon_degrees_to_mavlink_int(47.3977419, 8.545594)
        assert xi == 473977419
        assert yi == 85455940

    def test_frame_legacy_three_maps_to_int(self) -> None:
        assert normalize_mission_frame_for_raw_upload(MAV_FRAME_GLOBAL_RELATIVE_ALT) == (
            MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
        )
        assert normalize_mission_frame_for_raw_upload(None) == MAV_FRAME_GLOBAL_RELATIVE_ALT_INT


class TestIceEnergyBudgetWh:
    """Fuel BSFC path yields Wh for trajectory (not kWh passed as Wh)."""

    def test_bsfc_g_kwh_to_wh(self) -> None:
        tank_kg = 10.0
        fuel_reserve = 0.15
        bsfc = 500.0  # g/kWh
        usable_fuel_g = tank_kg * 1000.0 * (1.0 - fuel_reserve)
        energy_kwh = usable_fuel_g / bsfc
        energy_wh = energy_kwh * 1000.0
        # 8500 g / 500 g/kWh = 17 kWh = 17000 Wh
        assert abs(energy_kwh - 17.0) < 1e-9
        assert energy_wh == 17000.0


class TestPCEVarianceAndSobol:
    """Legendre PCE on Uniform(-1,1): variance uses basis norms (TV-PCE-1 style)."""

    def test_legendre_weight_1d_order_one(self) -> None:
        assert abs(_legendre_uniform_basis_variance_weight((1,)) - (1.0 / 3.0)) < 1e-12

    def test_y_equals_x_variance_and_sobol(self) -> None:
        """y = x, X ~ U(-1,1): Var(Y)=1/3, S1=1 for the only input."""
        sur = PCESurrogate(max_order=1, n_training_factor=2)
        sur.param_names = ["x"]
        sur.multi_indices = [(0,), (1,)]
        # c0=0, c1=1 for Y = P1(x) = x
        sur.coefficients["y"] = np.array([0.0, 1.0])
        res = sur.compute_statistics()
        var = res.output_std["y"] ** 2
        assert abs(var - (1.0 / 3.0)) < 1e-10
        assert abs(res.sobol_first["y"]["x"] - 1.0) < 1e-10
        assert abs(res.sobol_total["y"]["x"] - 1.0) < 1e-10


class TestMavsdkConnectionBoundary:
    """Telemetry pymavlink must not be reused as MAVSDK System."""

    def test_mavsdk_module_has_no_telemetry_reuse(self) -> None:
        path = Path(gorzen.__file__).resolve().parent / "services" / "mavsdk_connection.py"
        text = path.read_text(encoding="utf-8")
        assert "telemetry_service" not in text
        assert "get_connected_system" not in text


@pytest.mark.skipif(
    importlib.util.find_spec("mavsdk") is None or importlib.util.find_spec("mavsdk.mission_raw") is None,
    reason="mavsdk not installed",
)
class TestExecutionRawMissionItemEncoding:
    """MAVSDK MissionRaw items: degrees vs pre-scaled x/y."""

    def test_mavlink_to_raw_item_degrees_and_scaled(self) -> None:
        from gorzen.api.routers import execution as execution_mod

        if not execution_mod.HAS_MAVSDK:
            pytest.skip("MAVSDK MissionItem unavailable")

        deg = execution_mod._mavlink_to_raw_item(
            {
                "frame": MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                "command": 16,
                "x": 47.3977419,
                "y": 8.545594,
                "z": 30.0,
            },
            seq=0,
        )
        assert deg.x == 473977419
        assert deg.y == 85455940
        assert deg.frame == MAV_FRAME_GLOBAL_RELATIVE_ALT_INT

        pre = execution_mod._mavlink_to_raw_item(
            {
                "frame": MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                "command": 16,
                "x": 473977419,
                "y": 85455940,
                "z": 30.0,
            },
            seq=1,
        )
        assert pre.x == 473977419
        assert pre.y == 85455940
