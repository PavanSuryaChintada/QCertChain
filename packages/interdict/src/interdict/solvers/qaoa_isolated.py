"""QAOA in a dedicated worker process.

Why: COBYLA's evaluation loop is Python-heavy. Inside a busy host process (an API serving polls and SSE)
it competes for the GIL — measured 34 s inside the API vs 9.8 s standalone on the same 12-qubit problem.
A separate process has its own interpreter, and the parent can enforce a HARD wall-clock limit by
terminating the child, which an in-process timeout check cannot guarantee.
"""
from __future__ import annotations

import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

from interdict.types import Problem

_LOCK = threading.Lock()
_POOL: ProcessPoolExecutor | None = None
GRACE_S = 2.0  # child gets its own soft limit; the parent kills it this long after the hard limit


def _warm() -> None:
    import qiskit  # noqa: F401  load once per child, not per solve
    import qiskit_aer  # noqa: F401


def _run(p: Problem, child_timeout_s: float):
    from interdict.solvers.qaoa import solve_qaoa
    return solve_qaoa(p, timeout_s=child_timeout_s)


def _pool() -> ProcessPoolExecutor:
    global _POOL
    with _LOCK:
        if _POOL is None:
            _POOL = ProcessPoolExecutor(max_workers=1, initializer=_warm)
        return _POOL


def warm() -> None:
    """Start the child and import Qiskit now (API startup), so the first benchmark is not slower."""
    _pool().submit(int).result(timeout=120)


def shutdown() -> None:
    global _POOL
    with _LOCK:
        pool, _POOL = _POOL, None
    if pool is not None:
        for proc in list(getattr(pool, "_processes", {}).values()):
            proc.terminate()
        pool.shutdown(wait=False, cancel_futures=True)


def solve_qaoa_isolated(p: Problem, timeout_s: float = 15.0, _child_timeout_s: float | None = None):
    # Worker start-up (spawn + Qiskit import, ~8 s measured) is NOT the solver's time: wait for a warm worker
    # first, then start the solve clock. Otherwise one kill cascades into timeouts on every later call.
    warm()
    fut = _pool().submit(_run, p, timeout_s if _child_timeout_s is None else _child_timeout_s)
    try:
        return fut.result(timeout=timeout_s + GRACE_S)
    except FuturesTimeout:
        shutdown()  # the child overran: kill it, and warm a replacement in the background right away
        threading.Thread(target=warm, daemon=True).start()
        raise TimeoutError(f"qaoa exceeded {timeout_s}s (process terminated)") from None
