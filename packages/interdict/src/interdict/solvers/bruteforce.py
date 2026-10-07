"""Exhaustive search: try every k-subset of takedown targets. Exact by construction, so at small n it PROVES what
CP-SAT found is optimal. Coverage only grows with more targets, so the k-subsets are all that need checking:
C(n, k) plans. That count is polynomial in n for a fixed k (~n^k) and explodes when k grows with n, which is where
maximum coverage is NP-hard.

Bitsets keep each plan cheap: a node's coverage is an int bitmask over domains, and a plan's objective is a few
popcounts (one per distinct domain weight).
"""
from __future__ import annotations

import itertools
import math

from interdict.types import Problem

MAX_NODES = 22         # the scaling benchmark measures exhaustive search up to here and extrapolates beyond
MAX_PLANS = 2_000_000  # a campaign benchmark runs the exhaustive row only if C(n, k) is at most this (~20 s)


def solve_bruteforce(p: Problem, max_plans: int = MAX_PLANS) -> tuple[list[str], int]:
    """Returns (best targets, number of plans checked)."""
    n = len(p.nodes)
    k = min(p.k, n)
    plans = math.comb(n, k) if n else 1
    if plans > max_plans:
        raise ValueError(f"skipped: C({n}, {k}) = {plans:,} plans exceeds {max_plans:,}; 2^{n} possible takedown "
                         "sets in total")
    if k <= 0 or n == 0:
        return [], 1
    domains = list(p.deps)
    index = {d: i for i, d in enumerate(domains)}
    masks = {v: 0 for v in p.nodes}
    for d, s in p.deps.items():
        for v in s:
            if v in masks:
                masks[v] |= 1 << index[d]
    buckets: dict[float, int] = {}
    for d in domains:
        buckets[p.weights[d]] = buckets.get(p.weights[d], 0) | (1 << index[d])
    weighted = list(buckets.items())
    node_masks = [masks[v] for v in p.nodes]
    best_val, best = -1.0, ()
    for combo in itertools.combinations(range(n), k):
        m = 0
        for i in combo:
            m |= node_masks[i]
        val = sum(w * (m & b).bit_count() for w, b in weighted)
        if val > best_val:  # strict: the first (lexicographically smallest) optimum wins, deterministically
            best_val, best = val, combo
    return [p.nodes[i] for i in best], math.comb(n, k)
