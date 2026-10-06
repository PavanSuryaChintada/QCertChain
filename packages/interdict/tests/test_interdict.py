"""RELEASE GATE (CLAUDE.md §6): 500 random instances, never over budget, coverage computed correctly."""
import itertools
import random
import time

import pytest

from interdict.solvers.cpsat import solve_cpsat
from interdict.solvers.greedy import solve_greedy
from interdict.types import Plan, Problem
from interdict.validate import PlanInvalid, validate


def rand_problem(rng, n_nodes=None, n_dom=None, k=None):
    n_nodes = n_nodes or rng.randint(1, 15)
    n_dom = n_dom or rng.randint(1, 60)
    nodes = tuple(f"n{i}" for i in range(n_nodes))
    deps = {f"d{j}": frozenset(rng.sample(nodes, rng.randint(0, min(3, n_nodes)))) for j in range(n_dom)}
    w = {d: rng.choice([1.0, 1.0, 2.5]) for d in deps}
    return Problem(nodes, deps, w, k if k is not None else rng.randint(0, 6))


def brute(p):
    best = 0.0
    for r in range(min(p.k, len(p.nodes)) + 1):
        for c in itertools.combinations(p.nodes, r):
            best = max(best, p.objective(c))
    return best


@pytest.mark.parametrize("seed", range(500))
def test_500_random_instances_budget_and_coverage(seed):
    p = rand_problem(random.Random(seed))
    for solver in (solve_greedy, solve_cpsat):
        t = solver(p)
        killed = validate(p, t)
        assert len(t) <= p.k
        assert killed == {d for d, s in p.deps.items() if s & set(t)}


@pytest.mark.parametrize("seed", range(60))
def test_cpsat_is_optimal_on_small(seed):
    p = rand_problem(random.Random(1000 + seed), n_nodes=8, n_dom=25)
    assert p.objective(solve_cpsat(p)) == pytest.approx(brute(p))


def test_greedy_meets_1_minus_1_over_e():
    for s in range(100):
        p = rand_problem(random.Random(s), n_nodes=9, n_dom=30)
        assert p.objective(solve_greedy(p)) >= (1 - 1 / 2.718281828) * brute(p) - 1e-9


def test_validate_rejects_over_budget_unknown_and_duplicates():
    p = Problem(("a", "b"), {"d": frozenset({"a"})}, {"d": 1.0}, 1)
    with pytest.raises(PlanInvalid):
        validate(p, ["a", "b"])
    with pytest.raises(PlanInvalid):
        validate(p, ["zzz"])
    with pytest.raises(PlanInvalid):
        validate(Problem(("a", "b"), {"d": frozenset({"a"})}, {"d": 1.0}, 2), ["a", "a"])


def test_k_zero_and_k_above_nodes():
    p = Problem(("a",), {"d": frozenset({"a"})}, {"d": 1.0}, 0)
    assert solve_cpsat(p) == [] and solve_greedy(p) == []
    p2 = Problem(("a",), {"d": frozenset({"a"})}, {"d": 1.0}, 9)
    assert solve_cpsat(p2) == ["a"] and solve_greedy(p2) == ["a"]


def test_domain_with_no_takedownable_dependency_is_never_killed():
    p = Problem(("a",), {"d1": frozenset({"a"}), "d2": frozenset()}, {"d1": 1.0, "d2": 5.0}, 1)
    assert p.coverage(solve_cpsat(p)) == {"d1"}


def test_fractional_weights_respected():
    p = Problem(("a", "b"), {"d1": frozenset({"a"}), "d2": frozenset({"b"})}, {"d1": 1.4, "d2": 1.6}, 1)
    assert solve_cpsat(p) == ["b"] and solve_greedy(p) == ["b"]


def test_plan_coverage_pct():
    plan = Plan(backend="greedy", targets=["a"], killed={"d1"}, objective=1.0, domains_total=4, solve_ms=1, valid=True)
    assert plan.coverage_pct == 25.0


def campaign_shaped(seed=7, n=400):
    """Seed-like structure: domains Zipf-assigned to 12 IPs, 4 nameservers, 3 registrars."""
    rng = random.Random(seed)
    def zipf(prefix, k):
        w = [1 / (i + 1) ** 1.3 for i in range(k)]
        return [f"{prefix}{i}" for i in range(k)], w
    ips, wi = zipf("ip", 12)
    ns, wn = zipf("ns", 4)
    rg, wr = zipf("reg", 3)
    deps = {f"d{j}": frozenset({rng.choices(ips, wi)[0], rng.choices(ns, wn)[0], rng.choices(rg, wr)[0]})
            for j in range(n)}
    return Problem(tuple(ips + ns + rg), deps, {d: 1.0 for d in deps}, 5)


def test_cpsat_campaign_shaped_400_domains_optimal_under_1s():
    p = campaign_shaped()
    stats = {}
    t = time.perf_counter()
    solve_cpsat(p, timeout_s=10, stats=stats)
    assert time.perf_counter() - t < 1.0
    assert stats["status"] == "OPTIMAL"


def test_cpsat_hard_random_respects_time_limit_and_reports_gap():
    rng = random.Random(7)
    nodes = tuple(f"n{i}" for i in range(30))
    deps = {f"d{j}": frozenset(rng.sample(nodes, 3)) for j in range(400)}
    p = Problem(nodes, deps, {d: 1.0 for d in deps}, 5)
    stats = {}
    t = time.perf_counter()
    targets = solve_cpsat(p, timeout_s=0.9, stats=stats)
    assert time.perf_counter() - t < 1.5
    assert p.objective(targets) >= p.objective(solve_greedy(p))
    assert stats["status"] in ("OPTIMAL", "FEASIBLE")
    if stats["status"] == "FEASIBLE":
        assert stats["bound"] >= p.objective(targets) and stats["gap_pct"] >= 0


def test_cpsat_collapses_identical_signatures():
    deps = {f"d{j}": frozenset({"a"}) for j in range(300)} | {f"e{j}": frozenset({"b"}) for j in range(5)}
    p = Problem(("a", "b"), deps, {d: 1.0 for d in deps}, 1)
    stats = {}
    assert solve_cpsat(p, stats=stats) == ["a"]
    assert stats["n_groups"] == 2
