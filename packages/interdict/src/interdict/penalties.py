"""Runtime penalty calibration (NPHARD.md §6). Never hardcoded.

1.2 is the smallest safe margin: lambda must exceed the most a constraint violation can gain, but
oversized penalties flatten the landscape and stall COBYLA inside QAOA."""
from __future__ import annotations

from collections.abc import Mapping


def penalties(weights: Mapping[str, float]) -> tuple[float, float]:
    """(lam1, lam2). lam2 (budget) must exceed the gain of any extra node: 1.2 x total weight.
    lam1 (1.2 x max weight) is the spec's coverage penalty; the x-only formulation in qubo.py
    has no coverage constraint and does not use it."""
    return round(1.2 * max(weights.values(), default=0.0), 10), round(1.2 * sum(weights.values()), 10)
