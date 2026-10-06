"""solve(): fallback chain + validation gate (NPHARD.md §8). Default backend is cpsat; QAOA is opt-in.

Every exception from a backend, ImportError included, moves to the next solver in the chain.
Greedy is last and cannot fail; if it does, that is a genuine bug and it propagates.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from interdict.reduce import reduce
from interdict.solvers.annealing import solve_annealing
from interdict.solvers.cpsat import solve_cpsat
from interdict.solvers.greedy import solve_greedy
from interdict.types import Plan, Problem
from interdict.validate import validate

CHAINS = {
    "cpsat": ["cpsat", "greedy"],
    "qaoa": ["qaoa", "cpsat", "greedy"],
    "annealing": ["annealing", "cpsat", "greedy"],
    "greedy": ["greedy"],
}


@dataclass
class SolverOutput:
    targets: list[str]
    qubit_count: int | None = None
    notes: list[str] = field(default_factory=list)


def _cpsat(p: Problem, *, timeout_s: float, max_vars: int) -> SolverOutput:
    stats: dict = {}
    targets = solve_cpsat(p, timeout_s=timeout_s, stats=stats)
    note = f"cp-sat {stats['status'].lower()}"
    if stats["status"] != "OPTIMAL":
        note += f" (time limit; gap {stats['gap_pct']}%)"
    return SolverOutput(targets, notes=[note])


def _greedy(p: Problem, *, timeout_s: float, max_vars: int) -> SolverOutput:
    return SolverOutput(solve_greedy(p))


def _annealing(p: Problem, *, timeout_s: float, max_vars: int) -> SolverOutput:
    r = reduce(p, max_vars=max_vars)
    return SolverOutput(solve_annealing(r.problem), notes=r.notes)


# Hosts that serve other work in the same process (the API) set this True: QAOA then runs in a dedicated
# process with a hard wall-clock limit (see solvers/qaoa_isolated.py). Default: in-process.
ISOLATE_QAOA = False


def _qaoa(p: Problem, *, timeout_s: float, max_vars: int) -> SolverOutput:
    r = reduce(p, max_vars=max_vars)
    if ISOLATE_QAOA:
        from interdict.solvers import qaoa_isolated
        targets, qubits = qaoa_isolated.solve_qaoa_isolated(r.problem, timeout_s=timeout_s)
    else:
        from interdict.solvers.qaoa import solve_qaoa  # lazy: the package must import without Qiskit
        targets, qubits = solve_qaoa(r.problem, timeout_s=timeout_s)
    return SolverOutput(targets, qubit_count=qubits, notes=r.notes)


SOLVERS = {"cpsat": _cpsat, "greedy": _greedy, "annealing": _annealing, "qaoa": _qaoa}


def run_one(p: Problem, backend: str, *, timeout_s: float, max_vars: int) -> tuple[SolverOutput, set[str], int]:
    if backend == "qaoa" and ISOLATE_QAOA:  # worker start-up is not solver time: warm before the clock starts
        from interdict.solvers import qaoa_isolated
        qaoa_isolated.warm()
    t0 = time.perf_counter()
    out = SOLVERS[backend](p, timeout_s=timeout_s, max_vars=max_vars)
    ms = int((time.perf_counter() - t0) * 1000)
    killed = validate(p, out.targets)
    return out, killed, ms


def solve(p: Problem, backend: str = "cpsat", timeout_s: float = 10.0, max_vars: int = 24) -> Plan:
    if backend not in CHAINS:
        raise ValueError(f"unknown backend {backend!r}; expected one of {sorted(CHAINS)}")
    n_vars = reduce(p, max_vars=max_vars).n_variables
    chain = CHAINS[backend]
    failures: list[str] = []
    for i, name in enumerate(chain):
        try:
            out, killed, ms = run_one(p, name, timeout_s=timeout_s, max_vars=max_vars)
        except Exception as e:  # every backend failure, ImportError included, falls through
            if i == len(chain) - 1:
                raise
            failures.append(f"{name}: {type(e).__name__}: {e}")
            continue
        return Plan(backend=name, targets=out.targets, killed=killed, objective=p.objective(out.targets),
                    domains_total=len(p.deps), solve_ms=ms, valid=True,
                    fell_back=i > 0, fallback_from=backend if i > 0 else None,
                    n_variables=n_vars, qubit_count=out.qubit_count, notes=failures + out.notes)
    raise AssertionError("unreachable")
