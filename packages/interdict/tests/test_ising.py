"""QAOA backend: Ising sign convention verified by brute force (NPHARD.md §7), plus behaviour."""
import itertools
import time

import pytest

pytest.importorskip("qiskit")
pytest.importorskip("qiskit_aer")

from interdict.qubo import build_qubo, qubo_energy  # noqa: E402
from interdict.solvers.qaoa import qubo_to_ising, solve_qaoa  # noqa: E402
from interdict.types import Problem  # noqa: E402

pytestmark = pytest.mark.quantum


def test_ising_energy_matches_qubo_for_every_bitstring():
    p = Problem(("a", "b", "c", "d"),
                {"g1": frozenset({"a"}), "g2": frozenset({"b", "c"}), "g3": frozenset({"c", "d"})},
                {"g1": 2.0, "g2": 1.0, "g3": 3.0}, 2)
    Q, c, names = build_qubo(p)
    n = len(names)
    H, offset = qubo_to_ising(Q, c, n)
    diag = H.to_matrix(sparse=True).diagonal().real
    for bits in itertools.product([0, 1], repeat=n):
        idx = sum(b << i for i, b in enumerate(bits))  # qiskit is little-endian: qubit i = bit i
        assert diag[idx] + offset == pytest.approx(qubo_energy(Q, c, bits)), bits


def test_ising_ordering_matches_qubo_ordering():
    p = Problem(("a", "b", "c"), {"g1": frozenset({"a"}), "g2": frozenset({"b"}), "g3": frozenset({"b", "c"})},
                {"g1": 5.0, "g2": 1.0, "g3": 1.0}, 1)
    Q, c, names = build_qubo(p)
    H, offset = qubo_to_ising(Q, c, len(names))
    diag = H.to_matrix(sparse=True).diagonal().real + offset
    order_ising = sorted(range(len(diag)), key=lambda i: (round(diag[i], 9), i))
    order_qubo = sorted(range(len(diag)), key=lambda i: (round(qubo_energy(
        Q, c, [(i >> q) & 1 for q in range(len(names))]), 9), i))
    assert order_ising == order_qubo


def test_qaoa_finds_optimum_on_small_instance():
    p = Problem(("a", "b", "c"), {f"d{i}": frozenset({"abc"[i % 3]}) for i in range(9)},
                {f"d{i}": 1.0 + (i % 3 == 0) for i in range(9)}, 1)
    targets, qubits = solve_qaoa(p, timeout_s=15)
    assert targets == ["a"] and qubits == 3


def test_qaoa_respects_budget_on_campaign_shaped_reduced_problem():
    from interdict.reduce import reduce
    from interdict.solvers.cpsat import solve_cpsat
    import random
    rng = random.Random(1)
    ips = [f"ip{i}" for i in range(12)]
    ns = [f"ns{i}" for i in range(4)]
    deps = {f"d{j}": frozenset({rng.choice(ips[:6]), rng.choice(ns)}) for j in range(200)}
    full = Problem(tuple(ips + ns), deps, {d: 1.0 for d in deps}, 3)
    r = reduce(full)
    t0 = time.perf_counter()
    targets, qubits = solve_qaoa(r.problem, timeout_s=15)
    assert time.perf_counter() - t0 < 15  # CLAUDE.md §5: QAOA (<=24 qubits) < 15 s
    assert len(targets) <= 3 and qubits == len(r.problem.nodes) <= 24
    assert full.objective(targets) <= full.objective(solve_cpsat(full))  # never better than optimal


def test_too_many_variables_rejected():
    p = Problem(tuple(f"n{i}" for i in range(25)), {"g": frozenset({"n0"})}, {"g": 1.0}, 1)
    with pytest.raises(ValueError):
        solve_qaoa(p)


def test_timeout_raises():
    p = Problem(tuple(f"n{i}" for i in range(10)),
                {f"g{i}": frozenset({f"n{i}", f"n{(i + 1) % 10}"}) for i in range(10)},
                {f"g{i}": 1.0 for i in range(10)}, 3)
    with pytest.raises(TimeoutError):
        solve_qaoa(p, timeout_s=0.01)
