"""Performance benchmark for envelope solver.

Run from project root: python benchmarks/benchmark_envelope.py
"""

from __future__ import annotations

import time

from gorzen.schemas.twin_graph import VehicleTwin
from gorzen.solver.envelope_solver import compute_envelope


def main() -> None:
    twin = VehicleTwin()

    configs = [
        {"grid": 10, "mc": 100},
        {"grid": 20, "mc": 500},
        {"grid": 20, "mc": 1000},
        {"grid": 30, "mc": 500},
    ]

    print("Grid\tMC\tTime(s)\tMCP")
    print("-" * 40)
    for cfg in configs:
        t0 = time.perf_counter()
        resp = compute_envelope(
            twin,
            grid_resolution=cfg["grid"],
            mc_samples=cfg["mc"],
        )
        elapsed = time.perf_counter() - t0
        print(f"{cfg['grid']}\t{cfg['mc']}\t{elapsed:.2f}\t{resp.mission_completion_probability:.2f}")

    # Report from response
    resp = compute_envelope(twin, grid_resolution=20, mc_samples=1000)
    print(f"\nBaseline (20×20, 1000 MC): {resp.computation_time_s:.2f}s (from response)")


if __name__ == "__main__":
    main()
