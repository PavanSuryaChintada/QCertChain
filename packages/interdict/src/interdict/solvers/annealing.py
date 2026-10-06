"""Simulated annealing on the reduced QUBO. numpy only."""
from __future__ import annotations

import numpy as np

from interdict.qubo import build_qubo, decode
from interdict.types import Problem


def solve_annealing(p: Problem, seed: int = 0, sweeps: int = 4000) -> list[str]:
    Q, _, names = build_qubo(p)
    n = len(names)
    if n == 0 or p.k <= 0:
        return []
    M = np.zeros((n, n))  # symmetric form: E(x) = x^T M x (+ const)
    for (i, j), v in Q.items():
        if i == j:
            M[i, i] += v
        else:
            M[i, j] += v / 2
            M[j, i] += v / 2
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    x[rng.choice(n, size=min(p.k, n), replace=False)] = 1
    energy = x @ M @ x
    best, best_e = x.copy(), energy
    scale = max(float(np.abs(M).max()), 1e-9)
    t_hot, t_cold = scale, scale * 1e-4
    for step in range(sweeps):
        t = t_hot * (t_cold / t_hot) ** (step / max(sweeps - 1, 1))
        i = int(rng.integers(n))
        # energy change of flipping bit i
        delta = (1 - 2 * x[i]) * (M[i, i] + 2 * (M[i] @ x - M[i, i] * x[i]))
        if delta <= 0 or rng.random() < np.exp(-delta / t):
            x[i] = 1 - x[i]
            energy += delta
            if energy < best_e:
                best, best_e = x.copy(), energy
    chosen = decode([int(b) for b in best], names)
    if len(chosen) > p.k:  # budget penalty violated: keep the k with the largest marginal coverage
        kept: list[str] = []
        for _ in range(p.k):
            kept.append(max((c for c in chosen if c not in kept), key=lambda c: p.objective(kept + [c])))
        chosen = kept
    return chosen
