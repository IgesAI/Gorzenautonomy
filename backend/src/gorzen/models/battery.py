"""Battery model: Thevenin equivalent circuit, UKF SoC/SoH estimation, aging.

1RC Thevenin model with temperature-dependent parameters and aging.
"""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel


def lipo_ocv(soc: float) -> float:
    """Open-circuit voltage for a single LiPo cell as function of SoC (0-1).

    Polynomial fit to typical LiPo discharge curve.
    """
    soc = np.clip(soc, 0.0, 1.0)
    return (
        3.0
        + 1.2 * soc
        - 0.6 * soc ** 2
        + 0.6 * soc ** 3
    )


class BatteryModel(SubsystemModel):
    """1RC Thevenin equivalent-circuit battery model.

    Captures: OCV(SoC), R0(SoH, temp), R1/C1 dynamic response,
    temperature-dependent sag, and aging.
    """

    def parameter_names(self) -> list[str]:
        return [
            "cell_count_s", "cell_count_p", "capacity_ah",
            "internal_resistance_mohm", "soh_pct",
            "wiring_loss_mohm", "reserve_policy_pct",
            "r1_mohm", "c1_f",
        ]

    def state_names(self) -> list[str]:
        return ["soc", "v_rc1", "temperature_c"]

    def output_names(self) -> list[str]:
        return [
            "pack_voltage_V", "terminal_voltage_V",
            "soc_pct", "power_draw_W", "endurance_min",
            "energy_remaining_Wh", "reserve_time_min",
            "voltage_sag_V", "battery_feasible",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        n_s = int(params.get("cell_count_s", 6))
        n_p = int(params.get("cell_count_p", 1))
        cap_ah = params.get("capacity_ah", 10.0)
        r0_mohm = params.get("internal_resistance_mohm", 15.0)
        soh = params.get("soh_pct", 100.0) / 100.0
        wiring_mohm = params.get("wiring_loss_mohm", 5.0)
        reserve_pct = params.get("reserve_policy_pct", 20.0)
        r1_mohm = params.get("r1_mohm", 5.0)

        soc = conditions.get("soc", 0.9)
        I_draw = conditions.get("total_propulsion_power_W", 200.0)
        temp_c = conditions.get("temperature_c", 25.0)

        effective_cap = cap_ah * soh * n_p

        # Temperature correction for internal resistance
        temp_factor = 1.0 + 0.005 * (25.0 - temp_c)
        r0 = r0_mohm / 1000.0 * temp_factor / n_p
        r1 = r1_mohm / 1000.0 * temp_factor / n_p
        r_wiring = wiring_mohm / 1000.0

        ocv_cell = lipo_ocv(soc)
        ocv_pack = ocv_cell * n_s

        # Estimate current from power and OCV
        I_total = I_draw / (ocv_pack + 1e-6)

        # Voltage sag
        v_sag_r0 = I_total * r0
        v_sag_r1 = I_total * r1 * 0.63  # approximate steady-state for 1RC
        v_sag_wiring = I_total * r_wiring
        total_sag = v_sag_r0 + v_sag_r1 + v_sag_wiring

        terminal_v = ocv_pack - total_sag

        usable_soc = max(soc - reserve_pct / 100.0, 0.0)
        energy_remaining = usable_soc * effective_cap * ocv_pack
        endurance_min = (energy_remaining / (I_draw / 60.0 + 1e-9)) if I_draw > 1.0 else 999.0

        reserve_energy = (reserve_pct / 100.0) * effective_cap * ocv_pack
        reserve_time = (reserve_energy / (I_draw / 60.0 + 1e-9)) if I_draw > 1.0 else 999.0

        # Min voltage check (3.3V/cell under load)
        min_cell_v = 3.3
        feasible = terminal_v >= (min_cell_v * n_s) and soc > 0.05

        return ModelOutput(
            values={
                "pack_voltage_V": ocv_pack,
                "terminal_voltage_V": terminal_v,
                "soc_pct": soc * 100.0,
                "power_draw_W": I_draw,
                "endurance_min": endurance_min,
                "energy_remaining_Wh": energy_remaining,
                "reserve_time_min": reserve_time,
                "voltage_sag_V": total_sag,
                "battery_feasible": float(feasible),
            },
            units={
                "pack_voltage_V": "V", "terminal_voltage_V": "V",
                "soc_pct": "%", "power_draw_W": "W",
                "endurance_min": "min", "energy_remaining_Wh": "Wh",
                "reserve_time_min": "min", "voltage_sag_V": "V",
                "battery_feasible": "1",
            },
            feasible=feasible,
        )


class BatteryAgingModel:
    """Cycle-life and SoH prediction model.

    Capacity fade: capacity_fraction = 1 - alpha * cycles^beta
    Resistance growth: R_factor = 1 + gamma * cycles^delta
    """

    def __init__(
        self,
        alpha: float = 0.0002,
        beta: float = 0.8,
        gamma: float = 0.0003,
        delta: float = 0.9,
    ):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.delta = delta

    def capacity_fraction(self, cycles: float) -> float:
        return max(1.0 - self.alpha * cycles ** self.beta, 0.5)

    def resistance_factor(self, cycles: float) -> float:
        return 1.0 + self.gamma * cycles ** self.delta

    def soh_pct(self, cycles: float) -> float:
        return self.capacity_fraction(cycles) * 100.0


class BatteryUKF:
    """Unscented Kalman Filter for battery state estimation.

    State vector: [SoC, V_rc1]
    Measurement: terminal voltage
    """

    def __init__(self, n_s: int = 6, capacity_ah: float = 10.0, r0_ohm: float = 0.015):
        self.n_s = n_s
        self.capacity_ah = capacity_ah
        self.r0 = r0_ohm
        self.x = np.array([0.9, 0.0])  # [SoC, V_rc1]
        self.P = np.diag([0.01, 0.001])
        self.Q = np.diag([1e-5, 1e-4])
        self.R_meas = np.array([[0.01]])

    def predict(self, current_A: float, dt_s: float) -> None:
        soc, v_rc = self.x
        dsoc = -current_A * dt_s / (self.capacity_ah * 3600.0)
        r1, c1 = 0.005, 500.0
        dv_rc = -v_rc / (r1 * c1) + current_A / c1
        self.x = np.array([soc + dsoc, v_rc + dv_rc * dt_s])
        self.P = self.P + self.Q

    def update(self, measured_voltage: float) -> None:
        soc, v_rc = self.x
        ocv = lipo_ocv(soc) * self.n_s
        predicted_v = ocv - v_rc
        y = measured_voltage - predicted_v
        H = np.array([[-self.n_s * 1.2, -1.0]])  # linearized
        S = H @ self.P @ H.T + self.R_meas
        K = self.P @ H.T / (S[0, 0] + 1e-12)
        self.x = self.x + (K @ np.array([[y]])).flatten()
        self.P = (np.eye(2) - K @ H) @ self.P
        self.x[0] = np.clip(self.x[0], 0.0, 1.0)
