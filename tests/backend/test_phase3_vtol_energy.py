"""Phase 3b regression tests — VTOL phase-aware energy + BEMT rotor."""

from __future__ import annotations

import math

import pytest

from gorzen.solver.vtol_energy import (
    BEMTRotor,
    FlightPhase,
    MissionEnergyBreakdown,
    PhaseSegment,
    VTOLPhaseAwareEnergy,
)


def _small_rotor() -> BEMTRotor:
    return BEMTRotor(
        radius_m=0.45,
        chord_m=0.05,
        n_blades=3,
        tip_speed_ms=160.0,
    )


def _calculator() -> VTOLPhaseAwareEnergy:
    return VTOLPhaseAwareEnergy(
        mass_kg=5.0,
        rotor=_small_rotor(),
        n_rotors=4,
        wing_area_m2=0.5,
        wing_span_m=2.0,
        cd0=0.04,
        oswald_efficiency=0.75,
    )


class TestBEMTRotor:
    def test_hover_power_positive(self) -> None:
        rotor = _small_rotor()
        p = rotor.hover_power_w(thrust_n=15.0, rho=1.225)
        assert p > 0

    def test_hover_power_scales_with_thrust(self) -> None:
        rotor = _small_rotor()
        p1 = rotor.hover_power_w(10.0, 1.225)
        p2 = rotor.hover_power_w(40.0, 1.225)
        assert p2 > p1

    def test_forward_flight_reduces_induced_power(self) -> None:
        # With the same thrust, induced power is *lower* at modest forward
        # speed (the "helicopter sweet spot") because the rotor is pulling
        # in fresh air. Below that sweet spot profile + parasite growth
        # hasn't caught up yet.
        rotor = _small_rotor()
        p_hover = rotor.hover_power_w(15.0, 1.225)
        p_forward = rotor.forward_flight_power_w(15.0, 8.0, 1.225)
        assert p_forward < p_hover


class TestPhaseAwareEnergy:
    def test_hover_segment_burns_fixed_power(self) -> None:
        calc = _calculator()
        seg = PhaseSegment(phase=FlightPhase.HOVER, duration_s=60.0, altitude_m=50.0)
        result = calc.evaluate_segment(seg)
        assert result.power_w > 0
        assert result.energy_wh == pytest.approx(result.power_w * 60 / 3600, rel=1e-6)

    def test_hover_greater_than_cruise(self) -> None:
        calc = _calculator()
        hover = calc.evaluate_segment(
            PhaseSegment(phase=FlightPhase.HOVER, duration_s=60.0, altitude_m=50.0)
        )
        cruise = calc.evaluate_segment(
            PhaseSegment(
                phase=FlightPhase.CRUISE,
                duration_s=60.0,
                altitude_m=50.0,
                airspeed_ms=18.0,
            )
        )
        # Hover must burn more than cruise for an efficient fixed-wing aircraft.
        assert hover.power_w > cruise.power_w

    def test_transition_between_hover_and_cruise(self) -> None:
        calc = _calculator()
        v_mid = 0.5 * (calc.v_trans_start + calc.v_trans_end)
        p_hover = calc.hover_power_total_w(50.0)
        p_cruise = calc.cruise_power_fn(calc.v_trans_end + 2.0, 50.0)
        p_trans = calc.transition_power_w(v_mid, 50.0)
        assert min(p_cruise, p_hover) <= p_trans <= max(p_cruise, p_hover) * 1.05

    def test_evaluate_mission_partitions_energy(self) -> None:
        calc = _calculator()
        segments = [
            PhaseSegment(phase=FlightPhase.HOVER, duration_s=20.0, altitude_m=0.0),
            PhaseSegment(
                phase=FlightPhase.VTOL_CLIMB,
                duration_s=30.0,
                altitude_m=25.0,
                climb_rate_ms=3.0,
            ),
            PhaseSegment(
                phase=FlightPhase.TRANSITION_TO_FW,
                duration_s=15.0,
                altitude_m=50.0,
                airspeed_ms=10.0,
            ),
            PhaseSegment(
                phase=FlightPhase.CRUISE,
                duration_s=300.0,
                altitude_m=100.0,
                airspeed_ms=18.0,
            ),
            PhaseSegment(
                phase=FlightPhase.TRANSITION_TO_MC,
                duration_s=15.0,
                altitude_m=50.0,
                airspeed_ms=10.0,
            ),
            PhaseSegment(phase=FlightPhase.VTOL_DESCENT, duration_s=30.0, altitude_m=25.0),
            PhaseSegment(phase=FlightPhase.HOVER, duration_s=20.0, altitude_m=0.0),
        ]
        result = calc.evaluate_mission(segments)
        assert isinstance(result, MissionEnergyBreakdown)
        assert len(result.phases) == len(segments)
        assert result.total_duration_s == sum(s.duration_s for s in segments)
        assert result.total_energy_wh > 0
        by_phase = result.by_phase()
        # Hover + VTOL climb/descent together usually dominate in short missions.
        hover_energy = by_phase.get(FlightPhase.HOVER, 0.0)
        cruise_energy = by_phase.get(FlightPhase.CRUISE, 0.0)
        assert hover_energy > 0
        assert cruise_energy > 0

    def test_negative_duration_raises(self) -> None:
        calc = _calculator()
        seg = PhaseSegment(phase=FlightPhase.HOVER, duration_s=-1.0, altitude_m=0.0)
        with pytest.raises(ValueError):
            calc.evaluate_mission([seg])
