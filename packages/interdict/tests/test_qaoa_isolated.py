"""QAOA in a dedicated process: no GIL contention with a busy host process, and a HARD wall-clock limit."""
import threading
import time

import pytest

pytest.importorskip("qiskit")

from interdict.solvers.qaoa_isolated import shutdown, solve_qaoa_isolated  # noqa: E402
from interdict.types import Problem  # noqa: E402

pytestmark = pytest.mark.quantum

P = Problem(("a", "b", "c"), {f"d{i}": frozenset({"abc"[i % 3]}) for i in range(9)},
            {f"d{i}": 1.0 + (i % 3 == 0) for i in range(9)}, 1)


def test_isolated_solve_matches_in_process_answer():
    targets, qubits = solve_qaoa_isolated(P, timeout_s=30)
    assert targets == ["a"] and qubits == 3


def test_hard_timeout_is_enforced_even_if_the_child_overruns():
    t = time.perf_counter()
    with pytest.raises(TimeoutError):
        solve_qaoa_isolated(P, timeout_s=0.001, _child_timeout_s=120)  # child ignores the limit; parent must not
    assert time.perf_counter() - t < 6
    # The pool recovers, and starting the replacement worker (spawn + Qiskit import, ~8 s here) does NOT
    # count against the next solve's budget: a 6 s budget is enough for this 3-qubit solve on its own.
    targets, _ = solve_qaoa_isolated(P, timeout_s=6)
    assert targets == ["a"]


def test_busy_host_process_does_not_slow_the_solve():
    stop = threading.Event()

    def burn():
        while not stop.is_set():
            sum(i * i for i in range(10_000))

    threads = [threading.Thread(target=burn, daemon=True) for _ in range(4)]
    for th in threads:
        th.start()
    try:
        t = time.perf_counter()
        solve_qaoa_isolated(P, timeout_s=30)
        assert time.perf_counter() - t < 15
    finally:
        stop.set()
        shutdown()


def test_router_uses_isolated_process_when_enabled(monkeypatch):
    import interdict.router as r
    calls = []
    import interdict.solvers.qaoa_isolated as iso
    real = iso.solve_qaoa_isolated

    def spy(p, timeout_s=15.0, **kw):
        calls.append(timeout_s)
        return real(p, timeout_s=timeout_s, **kw)

    monkeypatch.setattr(iso, "solve_qaoa_isolated", spy)
    monkeypatch.setattr(r, "ISOLATE_QAOA", True)
    plan = r.solve(P, backend="qaoa", timeout_s=30)
    assert calls == [30] and plan.backend == "qaoa" and plan.qubit_count == 3 and plan.valid
