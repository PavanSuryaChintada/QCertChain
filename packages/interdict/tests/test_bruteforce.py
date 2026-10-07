"""Exhaustive search: at small n it PROVES the optimum, by checking every k-subset of takedown targets."""
import itertools
import math
import random

import pytest

from interdict.benchmark import benchmark
from interdict.solvers.bruteforce import MAX_PLANS, solve_bruteforce
from interdict.solvers.cpsat import solve_cpsat
from interdict.types import Problem


def _random_problem(rng, n, k, domains=60):
    nodes = tuple(f"n{i}" for i in range(n))
    deps = {f"d{j}": frozenset(rng.sample(nodes, rng.randint(1, 3))) for j in range(domains)}
    return Problem(nodes, deps, {d: float(rng.randint(1, 3)) for d in deps}, k)


def test_exhaustive_matches_cpsat_optimum_and_counts_every_plan():
    rng = random.Random(3)
    for _ in range(20):
        n, k = rng.randint(4, 12), rng.randint(1, 4)
        p = _random_problem(rng, n, k)
        targets, checked = solve_bruteforce(p)
        assert checked == math.comb(n, min(k, n))
        best = max(p.objective(c) for c in itertools.combinations(p.nodes, min(k, n)))
        assert p.objective(targets) == best == p.objective(solve_cpsat(p, timeout_s=5))


def test_exhaustive_refuses_above_the_plan_cap():
    p = _random_problem(random.Random(1), 60, 8)  # C(60, 8) = 2.6e9 plans
    assert math.comb(60, 8) > MAX_PLANS
    with pytest.raises(ValueError, match="2\\^60"):
        solve_bruteforce(p)


def test_exact_reduction_keeps_the_true_optimum_on_problems_too_big_to_enumerate_raw():
    from interdict.router import run_one
    rng = random.Random(11)
    nodes = tuple(f"n{i}" for i in range(40))
    # 40 nodes but heavy domination: most nodes cover a subset of a hub's domains
    deps = {f"d{j}": frozenset({f"n{j % 8}", f"n{8 + j % 32}"}) for j in range(160)}
    p = Problem(nodes, deps, {d: float(rng.randint(1, 3)) for d in deps}, 4)
    out, killed, _ = run_one(p, "bruteforce", timeout_s=30, max_vars=24)
    assert p.objective(out.targets) == p.objective(solve_cpsat(p, timeout_s=10)) and "exact reduction" in out.notes[0]


def test_benchmark_reports_exhaustive_row_or_why_it_was_skipped():
    small = _random_problem(random.Random(2), 10, 3)
    rows = {r.backend: r for r in benchmark(small, backends=("cpsat", "greedy", "bruteforce"))}
    assert rows["bruteforce"].valid and rows["bruteforce"].objective == rows["cpsat"].objective
    assert any("exhaustive" in n for n in rows["bruteforce"].notes)
    big = _random_problem(random.Random(2), 60, 8)
    rows = {r.backend: r for r in benchmark(big, backends=("cpsat", "bruteforce"))}
    assert not rows["bruteforce"].valid and rows["bruteforce"].error.startswith("skipped")
