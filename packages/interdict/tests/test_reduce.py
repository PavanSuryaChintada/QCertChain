import random

from interdict.reduce import collapse, reduce
from interdict.types import Problem


def mk(seed):
    rng = random.Random(seed)
    nodes = tuple(f"n{i}" for i in range(21))
    deps = {f"d{j}": frozenset(rng.sample(nodes[:6], 2)) for j in range(400)}
    return Problem(nodes, deps, {d: 1.0 for d in deps}, 5)


def test_collapse_preserves_total_weight_and_members():
    p = mk(1)
    cp, groups = collapse(p)
    assert sum(cp.weights.values()) == sum(p.weights.values())
    assert sorted(d for g in groups.values() for d in g) == sorted(p.domains)


def test_reduce_fits_cap():
    # x-only QUBO: one variable (qubit) per kept node
    r = reduce(mk(2), C=12, max_vars=24)
    assert len(r.problem.nodes) <= 12 and r.n_variables == len(r.problem.nodes)


def test_reduce_logs_when_it_shrinks_c():
    rng = random.Random(3)
    nodes = tuple(f"n{i}" for i in range(20))
    deps = {f"d{j}": frozenset(rng.sample(nodes, 2)) for j in range(600)}
    r = reduce(Problem(nodes, deps, {d: 1.0 for d in deps}, 3), C=12, max_vars=8)
    assert len(r.problem.nodes) <= 8
    assert any("lowered C" in n for n in r.notes)


def test_dominated_nodes_pruned():
    p = Problem(("a", "b"), {"d1": frozenset({"a", "b"}), "d2": frozenset({"b"})}, {"d1": 1, "d2": 1}, 1)
    assert reduce(p).problem.nodes == ("b",)


def test_nodes_covering_nothing_dropped():
    p = Problem(("a", "z"), {"d1": frozenset({"a"})}, {"d1": 1.0}, 1)
    assert reduce(p).problem.nodes == ("a",)


def test_groups_map_back_to_original_domains():
    p = mk(4)
    r = reduce(p)
    assert set(r.groups) == set(r.problem.domains)
    assert all(set(m) <= set(p.domains) for m in r.groups.values())
