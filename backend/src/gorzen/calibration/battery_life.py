"""Battery life estimator: empirical flight-time model from logs.

Ported from bolddrones/battery-life-estimator. Model: 1/T ≈ b0 + b1*payload + b2*v_air².
Calibrate from flight logs; estimate total and remaining time from voltage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

# LiPo voltage (per cell) to SOC mapping (typical curve, smoothed)
_LIPO_POINTS = np.array([
    [4.20, 1.00],
    [4.10, 0.90],
    [4.00, 0.80],
    [3.95, 0.70],
    [3.90, 0.60],
    [3.85, 0.50],
    [3.80, 0.40],
    [3.75, 0.32],
    [3.70, 0.26],
    [3.65, 0.20],
    [3.60, 0.14],
    [3.55, 0.08],
    [3.50, 0.04],
    [3.45, 0.02],
    [3.40, 0.01],
    [3.35, 0.005],
    [3.30, 0.0],
])


def soc_from_voltage_per_cell(v: float) -> float:
    """Map LiPo per-cell voltage to state of charge [0..1] via piecewise-linear interpolation."""
    xs = _LIPO_POINTS[:, 0]
    ys = _LIPO_POINTS[:, 1]
    v_clipped = max(min(v, float(xs.max())), float(xs.min()))
    soc = float(np.interp(v_clipped, xs[::-1], ys[::-1]))
    return max(0.0, min(1.0, soc))


@dataclass
class BatteryLifeModel:
    """Empirical flight-time model: inv_T = b0 + b1*payload_kg + b2*v_air²."""

    b0: float
    b1: float
    b2: float
    features: list[str] | None = None

    def predict_total_time_min(
        self,
        payload_kg: float,
        ground_speed_mps: float,
        headwind_mps: float = 0.0,
    ) -> float:
        """Predict total flight time in minutes for given conditions."""
        v_air = ground_speed_mps + headwind_mps
        inv_T = self.b0 + self.b1 * payload_kg + self.b2 * (v_air**2)
        inv_T = max(inv_T, 1e-9)
        return 1.0 / inv_T

    def predict_remaining_time_min(
        self,
        payload_kg: float,
        ground_speed_mps: float,
        headwind_mps: float,
        voltage_per_cell: float,
    ) -> float:
        """Predict remaining flight time from current voltage."""
        soc = soc_from_voltage_per_cell(voltage_per_cell)
        T_total = self.predict_total_time_min(payload_kg, ground_speed_mps, headwind_mps)
        return soc * T_total

    def to_dict(self) -> dict[str, Any]:
        return {
            "b0": self.b0,
            "b1": self.b1,
            "b2": self.b2,
            "features": self.features or ["1", "payload_kg", "v_air^2"],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BatteryLifeModel:
        return cls(
            b0=float(d["b0"]),
            b1=float(d["b1"]),
            b2=float(d["b2"]),
            features=d.get("features", ["1", "payload_kg", "v_air^2"]),
        )

    @classmethod
    def from_json(cls, s: str) -> BatteryLifeModel:
        return cls.from_dict(json.loads(s))


def fit_battery_model(
    flight_time_min: np.ndarray,
    payload_kg: np.ndarray,
    ground_speed_mps: np.ndarray,
    headwind_mps: np.ndarray,
) -> tuple[BatteryLifeModel, dict[str, float]]:
    """Fit BatteryLifeModel from flight log arrays. Returns (model, diagnostics)."""
    v_air = ground_speed_mps + headwind_mps
    X = np.vstack([payload_kg, v_air**2]).T
    inv_T = 1.0 / np.maximum(flight_time_min, 0.1)
    A = np.hstack([np.ones((len(X), 1)), X])
    b, *_ = np.linalg.lstsq(A, inv_T, rcond=None)
    model = BatteryLifeModel(b0=float(b[0]), b1=float(b[1]), b2=float(b[2]))

    pred_invT = b[0] + b[1] * X[:, 0] + b[2] * X[:, 1]
    pred_T = 1.0 / np.maximum(pred_invT, 1e-9)
    mae = float(np.mean(np.abs(pred_T - flight_time_min)))
    mape = float(100 * np.mean(np.abs((pred_T - flight_time_min) / (flight_time_min + 1e-9))))

    return model, {"mae_min": mae, "mape_pct": mape}
