"""Phase 2c regression tests — services raise instead of fabricating defaults."""

from __future__ import annotations

import pytest

from gorzen.schemas.mission import MissionPlan, Waypoint, WaypointType
from gorzen.services.mission_validator import (
    _check_energy_budget,
    _check_temperature,
    _check_wind_tolerance,
)


def _plan() -> MissionPlan:
    return MissionPlan(
        twin_id="test",
        waypoints=[
            Waypoint(
                sequence=0,
                wp_type=WaypointType.NAVIGATE,
                latitude_deg=37.0,
                longitude_deg=-122.0,
                altitude_m=50.0,
            )
        ],
    )


class TestEnergyBudgetFuelDefaults:
    def test_missing_fuel_density_is_insufficient_data(self) -> None:
        plan = _plan()
        plan.estimated_energy_wh = 100.0
        # _get walks nested paths; mirror that.
        params = {
            "fuel_system": {"tank_capacity_l": 5.0},
        }
        result = _check_energy_budget(plan, params)
        assert not result.passed
        assert "INSUFFICIENT_DATA" in result.detail

    def test_explicit_fuel_params_compute_wh(self) -> None:
        plan = _plan()
        plan.estimated_energy_wh = 1_000.0
        params = {
            "fuel_system": {
                "tank_capacity_l": 5.0,
                "fuel_density_kg_l": 0.72,
            },
            "fuel_heating_value_wh_per_kg": 12_000.0,
        }
        result = _check_energy_budget(plan, params)
        # 5 L * 0.72 kg/L * 12000 Wh/kg * 0.8 reserve factor = 34560 Wh usable
        assert result.limit > 30_000


class TestWindToleranceFailFast:
    def test_no_env_is_insufficient_data(self) -> None:
        result = _check_wind_tolerance(
            {"airframe.max_crosswind_kts": 20.0}, environment=None
        )
        assert not result.passed
        assert "INSUFFICIENT_DATA" in result.detail

    def test_missing_wind_speed_is_insufficient_data(self) -> None:
        result = _check_wind_tolerance(
            {"airframe.max_crosswind_kts": 20.0},
            environment={"temperature_c": 15.0},  # has env but no wind
        )
        assert not result.passed
        assert "INSUFFICIENT_DATA" in result.detail


class TestTemperatureFailFast:
    def test_only_max_provided_is_insufficient_data(self) -> None:
        result = _check_temperature(
            {"airframe.max_operating_temp_c": 45.0},
            environment={"temperature_c": 30.0},
        )
        assert not result.passed
        assert "INSUFFICIENT_DATA" in result.detail


class TestTerrainRaisesOnEmptyResults:
    @pytest.mark.asyncio
    async def test_terrain_raises_on_empty_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from gorzen.services import terrain as terrain_mod

        class _FakeResp:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"results": []}

        class _FakeClient:
            def __init__(self, *a, **kw) -> None:
                pass

            async def __aenter__(self) -> "_FakeClient":
                return self

            async def __aexit__(self, *a) -> None:
                return None

            async def get(self, url: str, params: dict) -> _FakeResp:
                return _FakeResp()

        monkeypatch.setattr(terrain_mod, "httpx", type("httpx", (), {"AsyncClient": _FakeClient}))
        with pytest.raises(terrain_mod.TerrainDataUnavailableError):
            await terrain_mod.fetch_elevation(37.0, -122.0)
