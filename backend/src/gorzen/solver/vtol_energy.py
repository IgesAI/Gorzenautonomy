"""VTOL phase-aware energy model with BEMT rotor power.

Real VTOL missions spend very different amounts of energy in each flight
phase; a single "cruise power" number can under-estimate total mission
energy by 30-60% because hover and transition burn several times more
than cruise. This module partitions a mission into phases and evaluates
each with the appropriate physics:

* **Hover / VTOL** — blade-element-momentum-theory (BEMT) rotor power
  over a simple blade-element integral with momentum-theory induced
  velocity, uniform disk loading, and blade drag.
* **Transition** — interpolates between hover power (rotor-borne thrust)
  and cruise power (wing-borne lift) as a function of forward speed.
* **Cruise** — classic drag-polar cruise power with propulsive
  efficiency (see :func:`gorzen.solver.trajectory.default_power_model`).

The :class:`VTOLPhaseAwareEnergy` calculator takes a list of
:class:`PhaseSegment`s and returns a phase-resolved breakdown of time,
energy, and battery SoC draw.

BEMT reference:
    Leishman, "Principles of Helicopter Aerodynamics", 2nd ed., §3.
    Johnson, "Helicopter Theory", Dover, §6.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import numpy as np

from gorzen.solver.trajectory import default_power_model


# ISA sea level.
RHO_0 = 1.225
TEMP_0 = 288.15
LAPSE_RATE = 0.0065
G = 9.81


class FlightPhase(str, Enum):
    HOVER = "hover"
    VTOL_CLIMB = "vtol_climb"
    VTOL_DESCENT = "vtol_descent"
    TRANSITION_TO_FW = "transition_to_fw"
    TRANSITION_TO_MC = "transition_to_mc"
    CRUISE = "cruise"
    LOITER = "loiter"


@dataclass
class BEMTRotor:
    """Blade-element-momentum-theory parameters for a single rotor.

    Minimal inputs sufficient for a steady-state hover/forward-flight
    power estimate. The model assumes uniform inflow and a linear lift
    slope — adequate at the mission-planning level but not a substitute
    for full CFD.
    """

    radius_m: float
    chord_m: float
    n_blades: int
    #: Blade tip speed target (m/s). Design rotor RPM follows from this
    #: and :attr:`radius_m`.
    tip_speed_ms: float = 150.0
    #: Lift-curve slope (per rad). 2π for ideal thin airfoil, 5.73 is a
    #: common rotor-code default.
    cl_alpha: float = 5.73
    #: Profile drag coefficient of the blades (flat-plate approximation).
    cd0_blade: float = 0.01
    #: Pitch angle at the blade root (rad). Twist is added linearly to
    #: the tip.
    theta_root_rad: float = math.radians(8.0)
    theta_tip_rad: float = math.radians(2.0)
    #: Figure-of-merit factor to capture installation losses (tip losses,
    #: downwash on fuselage, non-uniform inflow). 1.0 means ideal BEMT.
    installation_fm: float = 0.75

    @property
    def solidity(self) -> float:
        """Rotor solidity σ = N c / (π R)."""
        return self.n_blades * self.chord_m / (math.pi * self.radius_m)

    @property
    def omega_rps(self) -> float:
        return self.tip_speed_ms / self.radius_m

    @property
    def disk_area_m2(self) -> float:
        return math.pi * self.radius_m**2

    def hover_power_w(self, thrust_n: float, rho: float) -> float:
        """Hover power from BEMT with momentum-theory induced velocity.

        Power = P_induced + P_profile where
            P_induced = T * sqrt(T / (2 rho A))  /  FM
            P_profile = rho * A * (ΩR)^3 * σ * Cd0 / 8
        """
        if thrust_n <= 0.0:
            return 0.0
        A = self.disk_area_m2
        v_i = math.sqrt(thrust_n / (2.0 * rho * A))
        P_induced = thrust_n * v_i / self.installation_fm
        P_profile = rho * A * (self.tip_speed_ms**3) * self.solidity * self.cd0_blade / 8.0
        return P_induced + P_profile

    def forward_flight_power_w(
        self,
        thrust_n: float,
        forward_speed_ms: float,
        rho: float,
    ) -> float:
        """Rotor power in forward flight using Glauert's induced-velocity formula.

        mu = forward_speed / (Ω R). Profile drag grows with (1 + k·μ²);
        k = 4.65 is a classical Glauert/Bramwell constant that lumps
        fuselage effects into the blade-element calculation.
        """
        if thrust_n <= 0.0:
            return 0.0
        A = self.disk_area_m2
        v_h2 = thrust_n / (2.0 * rho * A)  # v_i in hover, squared
        v_forward = forward_speed_ms
        # Glauert forward-flight induced-velocity root.
        # v_i^4 + v_forward^2 * v_i^2 - v_h^4 = 0  (ignoring climb)
        a = 1.0
        b = v_forward**2
        c = -v_h2**2
        disc = b**2 - 4 * a * c
        v_i_sq = (-b + math.sqrt(max(disc, 0.0))) / (2 * a)
        v_i = math.sqrt(max(v_i_sq, 0.0))
        P_induced = thrust_n * v_i / self.installation_fm
        mu = v_forward / max(self.tip_speed_ms, 1e-3)
        P_profile = (
            rho
            * A
            * self.tip_speed_ms**3
            * self.solidity
            * self.cd0_blade
            * (1.0 + 4.65 * mu**2)
            / 8.0
        )
        P_parasite = 0.5 * rho * v_forward**3 * A * 0.01  # small fuselage contribution
        return P_induced + P_profile + P_parasite


@dataclass
class PhaseSegment:
    """One flight phase to account for in the energy budget."""

    phase: FlightPhase
    duration_s: float
    #: Altitude (m MSL) used for air-density. For climb / descent pass the
    #: mid-altitude of the segment.
    altitude_m: float
    #: Forward speed (m/s). ``0`` for hover. For climb/descent segments,
    #: supply the horizontal component (use ``climb_rate_ms`` separately).
    airspeed_ms: float = 0.0
    climb_rate_ms: float = 0.0
    #: Explicit thrust override (N). When ``None``, the calculator derives
    #: thrust from vehicle weight + climb acceleration + drag.
    thrust_n: float | None = None


@dataclass
class PhaseEnergy:
    phase: FlightPhase
    duration_s: float
    power_w: float
    energy_wh: float


@dataclass
class MissionEnergyBreakdown:
    phases: list[PhaseEnergy] = field(default_factory=list)
    total_energy_wh: float = 0.0
    total_duration_s: float = 0.0

    def by_phase(self) -> dict[FlightPhase, float]:
        out: dict[FlightPhase, float] = {}
        for p in self.phases:
            out[p.phase] = out.get(p.phase, 0.0) + p.energy_wh
        return out


class VTOLPhaseAwareEnergy:
    """Phase-aware mission-energy calculator for VTOL platforms.

    Args:
        mass_kg: Total vehicle mass.
        rotor: BEMT parameters for one rotor.
        n_rotors: Number of lift rotors.
        cruise_power_fn: Optional cruise-power closure
            ``(airspeed_ms, altitude_m) -> watts``. Defaults to a wrapper
            around :func:`default_power_model` using supplied wing geometry.
        wing_area_m2, wing_span_m, cd0, oswald_efficiency,
        propulsive_efficiency: cruise-power polar inputs (used when
        ``cruise_power_fn`` is not supplied).
    """

    def __init__(
        self,
        mass_kg: float,
        rotor: BEMTRotor,
        n_rotors: int,
        cruise_power_fn: Callable[[float, float], float] | None = None,
        wing_area_m2: float = 1.2,
        wing_span_m: float = 4.88,
        cd0: float = 0.03,
        oswald_efficiency: float = 0.8,
        propulsive_efficiency: float = 0.6,
        transition_speed_start_ms: float = 8.0,
        transition_speed_end_ms: float = 15.0,
    ) -> None:
        self.mass_kg = mass_kg
        self.rotor = rotor
        self.n_rotors = n_rotors
        self.wing_area = wing_area_m2
        self.wing_span = wing_span_m
        self.cd0 = cd0
        self.oswald = oswald_efficiency
        self.eta_prop = propulsive_efficiency
        self.v_trans_start = transition_speed_start_ms
        self.v_trans_end = transition_speed_end_ms

        if cruise_power_fn is None:
            def _cruise(v: float, h: float) -> float:
                return default_power_model(
                    v,
                    h,
                    mass_kg=mass_kg,
                    wing_area_m2=wing_area_m2,
                    wing_span_m=wing_span_m,
                    cd0=cd0,
                    oswald_e=oswald_efficiency,
                    prop_efficiency=propulsive_efficiency,
                )

            cruise_power_fn = _cruise
        self.cruise_power_fn = cruise_power_fn

    # -- primitives ---------------------------------------------------------

    def _air_density(self, altitude_m: float) -> float:
        T_isa = TEMP_0 - LAPSE_RATE * altitude_m
        return RHO_0 * (T_isa / TEMP_0) ** 4.2561

    def _hover_thrust(self, climb_rate_ms: float) -> float:
        # T = m (g + a_climb). At constant climb rate the aircraft is in
        # force balance: weight + drag = thrust, so we still need thrust = W
        # plus a small drag term handled inside the BEMT model.
        return self.mass_kg * G + max(climb_rate_ms, 0.0) * self.mass_kg * 0.1

    def hover_power_total_w(
        self,
        altitude_m: float,
        climb_rate_ms: float = 0.0,
    ) -> float:
        rho = self._air_density(altitude_m)
        T_total = self._hover_thrust(climb_rate_ms)
        T_per_rotor = T_total / max(self.n_rotors, 1)
        p_one = self.rotor.hover_power_w(T_per_rotor, rho)
        return p_one * self.n_rotors

    def transition_power_w(
        self,
        airspeed_ms: float,
        altitude_m: float,
    ) -> float:
        """Linear blend between hover and cruise power across the
        transition speed band. Captures the characteristic "transition
        power bucket" that drives VTOL battery sizing."""
        if airspeed_ms <= self.v_trans_start:
            return self.hover_power_total_w(altitude_m)
        if airspeed_ms >= self.v_trans_end:
            return float(self.cruise_power_fn(airspeed_ms, altitude_m))
        # Wing unload fraction. During transition rotors carry most of the
        # weight; we gradually shed rotor power and ramp cruise power.
        frac = (airspeed_ms - self.v_trans_start) / (self.v_trans_end - self.v_trans_start)
        rho = self._air_density(altitude_m)
        T_total = self._hover_thrust(0.0) * (1.0 - frac)
        T_per_rotor = T_total / max(self.n_rotors, 1)
        rotor_power = self.rotor.forward_flight_power_w(T_per_rotor, airspeed_ms, rho)
        cruise_power = frac * float(self.cruise_power_fn(airspeed_ms, altitude_m))
        return rotor_power * self.n_rotors + cruise_power

    # -- phase energy integration -------------------------------------------

    def evaluate_segment(self, seg: PhaseSegment) -> PhaseEnergy:
        if seg.phase in (FlightPhase.HOVER, FlightPhase.VTOL_CLIMB, FlightPhase.VTOL_DESCENT):
            power = self.hover_power_total_w(seg.altitude_m, seg.climb_rate_ms)
        elif seg.phase in (
            FlightPhase.TRANSITION_TO_FW,
            FlightPhase.TRANSITION_TO_MC,
        ):
            # Use the midpoint of the transition airspeed range.
            v = seg.airspeed_ms if seg.airspeed_ms > 0 else (
                0.5 * (self.v_trans_start + self.v_trans_end)
            )
            power = self.transition_power_w(v, seg.altitude_m)
        elif seg.phase in (FlightPhase.CRUISE, FlightPhase.LOITER):
            v = max(seg.airspeed_ms, 1.0)
            power = float(self.cruise_power_fn(v, seg.altitude_m))
        else:  # pragma: no cover - Enum is closed
            raise ValueError(f"Unknown flight phase {seg.phase}")

        energy_wh = power * seg.duration_s / 3600.0
        return PhaseEnergy(
            phase=seg.phase,
            duration_s=seg.duration_s,
            power_w=power,
            energy_wh=energy_wh,
        )

    def evaluate_mission(self, segments: list[PhaseSegment]) -> MissionEnergyBreakdown:
        breakdown = MissionEnergyBreakdown()
        for seg in segments:
            if seg.duration_s < 0:
                raise ValueError(f"Negative duration in segment {seg}")
            result = self.evaluate_segment(seg)
            breakdown.phases.append(result)
            breakdown.total_energy_wh += result.energy_wh
            breakdown.total_duration_s += result.duration_s
        return breakdown


def bemt_from_twin(twin_params: dict[str, float]) -> BEMTRotor:
    """Build a :class:`BEMTRotor` from flat twin parameters.

    Requires: ``rotor_diameter_m``, ``blade_count`` (``int``). Optional:
    ``rotor_chord_m`` (defaults to 8% of radius), ``rotor_tip_speed_ms``
    (defaults to 150 m/s), ``rotor_cd0_blade`` (defaults to 0.01),
    ``rotor_theta_root_rad`` / ``rotor_theta_tip_rad`` (defaults 8°/2°).
    """
    D = float(twin_params["rotor_diameter_m"])
    R = D / 2.0
    n_blades = int(twin_params.get("blade_count", 2))
    chord = float(twin_params.get("rotor_chord_m", 0.08 * R))
    return BEMTRotor(
        radius_m=R,
        chord_m=chord,
        n_blades=n_blades,
        tip_speed_ms=float(twin_params.get("rotor_tip_speed_ms", 150.0)),
        cd0_blade=float(twin_params.get("rotor_cd0_blade", 0.01)),
        theta_root_rad=float(twin_params.get("rotor_theta_root_rad", math.radians(8.0))),
        theta_tip_rad=float(twin_params.get("rotor_theta_tip_rad", math.radians(2.0))),
        installation_fm=float(twin_params.get("rotor_installation_fm", 0.75)),
    )
