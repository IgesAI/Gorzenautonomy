"""Chance constraints: probabilistic safety margin enforcement.

Supports both sampling-based and analytical approximations for
P(g(x, w) >= 0) >= 1 - epsilon.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np



@dataclass
class ChanceConstraintResult:
    """Result of chance constraint evaluation."""

    constraint_name: str
    probability_satisfied: float
    required_probability: float
    feasible: bool
    margin: float
    worst_case_value: float


def evaluate_chance_constraint(
    constraint_fn: Callable[[dict[str, float]], float],
    sample_inputs: dict[str, np.ndarray],
    threshold: float = 0.0,
    required_probability: float = 0.95,
    constraint_name: str = "",
) -> ChanceConstraintResult:
    """Evaluate a chance constraint via Monte Carlo sampling.

    constraint_fn returns a scalar: positive = satisfied, negative = violated.
    """
    n = len(next(iter(sample_inputs.values())))
    values = np.zeros(n)

    for i in range(n):
        inp = {k: float(v[i]) for k, v in sample_inputs.items()}
        try:
            values[i] = constraint_fn(inp)
        except Exception:
            values[i] = -1e6

    p_satisfied = float(np.mean(values >= threshold))
    worst = float(np.min(values))
    margin = p_satisfied - required_probability

    return ChanceConstraintResult(
        constraint_name=constraint_name,
        probability_satisfied=p_satisfied,
        required_probability=required_probability,
        feasible=p_satisfied >= required_probability,
        margin=margin,
        worst_case_value=worst,
    )


def joint_chance_constraint(
    constraint_fns: list[Callable[[dict[str, float]], float]],
    sample_inputs: dict[str, np.ndarray],
    required_probability: float = 0.95,
) -> tuple[float, list[ChanceConstraintResult]]:
    """Evaluate joint chance constraint: P(all constraints satisfied) >= threshold.

    Returns (joint_probability, individual_results).
    """
    n = len(next(iter(sample_inputs.values())))
    all_satisfied = np.ones(n, dtype=bool)
    results = []

    for i, fn in enumerate(constraint_fns):
        values = np.zeros(n)
        for j in range(n):
            inp = {k: float(v[j]) for k, v in sample_inputs.items()}
            try:
                values[j] = fn(inp)
            except Exception:
                values[j] = -1e6

        satisfied = values >= 0
        all_satisfied &= satisfied

        p = float(np.mean(satisfied))
        results.append(ChanceConstraintResult(
            constraint_name=f"constraint_{i}",
            probability_satisfied=p,
            required_probability=required_probability,
            feasible=p >= required_probability,
            margin=p - required_probability,
            worst_case_value=float(np.min(values)),
        ))

    joint_p = float(np.mean(all_satisfied))
    return joint_p, results
