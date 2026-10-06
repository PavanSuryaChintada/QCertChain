"""RELEASE GATE (CLAUDE.md §6): with Qiskit patched to fail on import, solve() still returns a valid plan."""
import builtins
import sys

import pytest

from interdict.benchmark import benchmark
from interdict.router import solve
from interdict.types import Problem

P = Problem(("a", "b"), {"d1": frozenset({"a"}), "d2": frozenset({"b"}), "d3": frozenset({"b"})},
            {"d1": 1.0, "d2": 1.0, "d3": 1.0}, 1)


@pytest.fixture
def no_qiskit(monkeypatch):
    real = builtins.__import__

    def fake(name, *a, **kw):
        if name.startswith("qiskit"):
            raise ImportError("qiskit patched out")
        return real(name, *a, **kw)

    for m in [m for m in sys.modules if m.startswith("qiskit")]:
        monkeypatch.delitem(sys.modules, m)
    monkeypatch.setattr(builtins, "__import__", fake)


def test_qaoa_without_qiskit_falls_back_to_cpsat(no_qiskit):
    plan = solve(P, backend="qaoa")
    assert plan.valid and plan.backend == "cpsat" and plan.fell_back and plan.fallback_from == "qaoa"
    assert plan.targets == ["b"] and plan.killed == {"d2", "d3"}
    assert plan.qubit_count is None


def test_package_imports_without_qiskit(no_qiskit):
    import importlib

    import interdict.router
    importlib.reload(interdict.router)


def test_default_backend_is_cpsat_and_not_fallen_back():
    plan = solve(P)
    assert plan.backend == "cpsat" and not plan.fell_back and plan.valid


def test_annealing_plan_valid_and_scored_on_full_problem():
    plan = solve(P, backend="annealing")
    assert plan.valid and len(plan.targets) <= 1 and plan.objective == 2.0


def test_benchmark_reports_failed_backend_row(no_qiskit):
    rows = benchmark(P)
    assert [r.backend for r in rows] == ["cpsat", "qaoa", "annealing", "greedy"]
    q = next(r for r in rows if r.backend == "qaoa")
    assert not q.valid and "qiskit" in q.error and q.objective == 0
    assert sum(r.is_best for r in rows) == 1
    assert next(r for r in rows if r.is_best).valid


def test_greedy_failure_raises(monkeypatch):
    import interdict.router as r
    monkeypatch.setitem(r.SOLVERS, "greedy", lambda p, **kw: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        solve(P, backend="greedy")


def test_every_backend_fails_except_greedy_still_returns_plan(monkeypatch):
    import interdict.router as r

    def boom(p, **kw):
        raise RuntimeError("down")

    monkeypatch.setitem(r.SOLVERS, "cpsat", boom)
    plan = solve(P, backend="qaoa")
    assert plan.backend == "greedy" and plan.fell_back and plan.fallback_from == "qaoa" and plan.valid


def test_unknown_backend_rejected():
    with pytest.raises(ValueError):
        solve(P, backend="magic")
