"""QUBO for maximum coverage — x-only formulation.

CORRECTION to NPHARD.md §6 (2026-10-06). The spec's coverage penalty
    lam1 * sum_g [ y_g - sum_{v in S(g)} x_v * y_g ]
REWARDS over-coverage: each extra selected node covering an already-covered group subtracts lam1.
The budget penalty does not cap it (both plans pick exactly k), so the ground state can be wrong:
g1={a,b} w5, g2={c} w1, k=2 -> the spec energy prefers {a,b} (-11) over the optimum {a,c} (-6).

Here a group's value is written directly on the node variables:
    value(g) = w_g * [1 - prod_{v in S(g)} (1 - x_v)]
             = w_g * [ sum_v x_v - sum_{u<v} x_u x_v + (terms of order >= 3) ]
Terms of order >= 3 are dropped. That is EXACT for groups with <= 2 dependencies and only
under-values a group whose >= 3 dependencies are ALL selected (a wasteful plan at small k).
Every plan is re-scored on the full problem, so the approximation can cost a backend objective,
never misreport one.

    H = -sum_g value_2(g) + lam2 * (sum_v x_v - k)^2,   k clipped to the node count.

One variable (qubit) per candidate node; no y variables.
Q is stored upper-triangular at (min(i,j), max(i,j)): writing both orders would double-count.
"""
from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations

from interdict.penalties import penalties
from interdict.types import Problem


def _add(Q: dict[tuple[int, int], float], i: int, j: int, v: float) -> None:
    key = (i, j) if i <= j else (j, i)
    Q[key] = Q.get(key, 0.0) + v


def build_qubo(p: Problem) -> tuple[dict[tuple[int, int], float], float, list[str]]:
    names = list(p.nodes)
    idx = {v: i for i, v in enumerate(names)}
    Q: dict[tuple[int, int], float] = {}
    for g, s in p.deps.items():
        w = p.weights[g]
        vs = sorted(idx[v] for v in s if v in idx)
        for i in vs:
            _add(Q, i, i, -w)
        for i, j in combinations(vs, 2):
            _add(Q, i, j, w)
    _, lam2 = penalties(p.weights)
    k = min(p.k, len(names))
    # lam2 * (sum x - k)^2 = lam2 * [ (1 - 2k) * sum x_i + 2 * sum_{i<j} x_i x_j + k^2 ]   since x^2 = x
    for i in range(len(names)):
        _add(Q, i, i, lam2 * (1 - 2 * k))
    for i, j in combinations(range(len(names)), 2):
        _add(Q, i, j, 2 * lam2)
    return Q, lam2 * k * k, names


def qubo_energy(Q: dict[tuple[int, int], float], const: float, bits: Sequence[int]) -> float:
    e = const
    for (i, j), v in Q.items():
        if bits[i] and bits[j]:
            e += v
    return e


def decode(bits: Sequence[int], names: list[str]) -> list[str]:
    return [n for b, n in zip(bits, names) if b]
