import pytest
import itertools

from interdict.penalties import penalties
from interdict.qubo import build_qubo, decode, qubo_energy
from interdict.types import Problem


def test_penalties_scale_with_weights():
    assert penalties({"a": 5.0, "b": 2.0}) == (6.0, 8.4)


def test_qubo_is_upper_triangular():
    p = Problem(("a", "b"), {"g1": frozenset({"a", "b"})}, {"g1": 1.0}, 1)
    Q, _, _ = build_qubo(p)
    assert all(i <= j for i, j in Q)


def test_qubo_minimum_is_the_optimal_plan():
    p = Problem(("a", "b", "c"),
                {"g1": frozenset({"a"}), "g2": frozenset({"b"}), "g3": frozenset({"b", "c"})},
                {"g1": 5.0, "g2": 1.0, "g3": 1.0}, 1)
    Q, c, names = build_qubo(p)
    best = min(itertools.product([0, 1], repeat=len(names)), key=lambda b: qubo_energy(Q, c, b))
    assert decode(best, names) == ["a"]


def test_qubo_ground_state_matches_bruteforce_coverage_on_random_instances():
    import random
    for seed in range(25):
        rng = random.Random(seed)
        nodes = ("a", "b", "c", "d")
        deps = {f"g{i}": frozenset(rng.sample(nodes, rng.randint(1, 2))) for i in range(5)}
        p = Problem(nodes, deps, {g: float(rng.randint(1, 5)) for g in deps}, 2)
        Q, c, names = build_qubo(p)
        best = min(itertools.product([0, 1], repeat=len(names)), key=lambda b: qubo_energy(Q, c, b))
        opt = max(p.objective(t) for t in itertools.combinations(nodes, 2))
        assert p.objective(decode(best, names)) == opt, seed


def test_k_above_node_count_does_not_force_impossible_budget():
    p = Problem(("a",), {"g": frozenset({"a"})}, {"g": 1.0}, 5)
    Q, c, names = build_qubo(p)
    best = min(itertools.product([0, 1], repeat=len(names)), key=lambda b: qubo_energy(Q, c, b))
    assert decode(best, names) == ["a"]


def test_overcoverage_is_not_rewarded():
    """Spec formulation (NPHARD §6) rewards a second node covering an already-covered group.
    g1={a,b} w5, g2={c} w1, k=2: the optimum is {a,c} (6), not {a,b} (5)."""
    p = Problem(("a", "b", "c"), {"g1": frozenset({"a", "b"}), "g2": frozenset({"c"})},
                {"g1": 5.0, "g2": 1.0}, 2)
    Q, c, names = build_qubo(p)
    best = min(itertools.product([0, 1], repeat=len(names)), key=lambda b: qubo_energy(Q, c, b))
    assert p.objective(decode(best, names)) == 6.0


def test_one_variable_per_node():
    p = Problem(("a", "b", "c"), {f"g{i}": frozenset({"a", "b", "c"}) for i in range(9)},
                {f"g{i}": 1.0 for i in range(9)}, 1)
    _, _, names = build_qubo(p)
    assert names == ["a", "b", "c"]


def test_energy_equals_minus_objective_when_budget_met_and_no_triple_cover():
    import random
    for seed in range(20):
        rng = random.Random(seed)
        nodes = tuple("abcde")
        deps = {f"g{i}": frozenset(rng.sample(nodes, rng.randint(1, 3))) for i in range(6)}
        p = Problem(nodes, deps, {g: float(rng.randint(1, 4)) for g in deps}, 2)
        Q, c, names = build_qubo(p)
        for pick in itertools.combinations(nodes, 2):  # 2 picks can never cover all 3 of a group
            bits = [1 if n in pick else 0 for n in names]
            assert qubo_energy(Q, c, bits) == pytest.approx(-p.objective(pick))
