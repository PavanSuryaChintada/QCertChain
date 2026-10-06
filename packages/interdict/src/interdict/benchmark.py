"""Run every backend on one problem and report every row — losses and failures included (NPHARD §10)."""
from __future__ import annotations

from dataclasses import dataclass, field

from interdict.reduce import reduce
from interdict.router import run_one
from interdict.types import Problem

GREEDY_GUARANTEE = "greedy is guaranteed >= (1 - 1/e) = 63.2% of optimal"


@dataclass
class BenchmarkRow:
    backend: str
    objective: float
    domains_killed: int
    domains_total: int
    coverage_pct: float
    solve_ms: int
    valid: bool
    targets: list[str]
    n_variables: int
    qubit_count: int | None
    is_best: bool = False
    error: str | None = None
    notes: list[str] = field(default_factory=list)


def benchmark(p: Problem, backends=("cpsat", "qaoa", "annealing", "greedy"), timeout_s: float = 15.0,
              max_vars: int = 24) -> list[BenchmarkRow]:
    n_vars = reduce(p, max_vars=max_vars).n_variables
    total = len(p.deps)
    rows: list[BenchmarkRow] = []
    for b in backends:  # each backend alone, no fallback chain: a failure is a row, not a substitution
        try:
            out, killed, ms = run_one(p, b, timeout_s=timeout_s, max_vars=max_vars)
            rows.append(BenchmarkRow(b, p.objective(out.targets), len(killed), total,
                                     round(100 * len(killed) / total, 2) if total else 0.0, ms, True,
                                     out.targets, n_vars, out.qubit_count, notes=out.notes))
        except Exception as e:
            rows.append(BenchmarkRow(b, 0.0, 0, total, 0.0, 0, False, [], n_vars, None,
                                     error=f"{type(e).__name__}: {e}"))
    valid = [r for r in rows if r.valid]
    if valid:
        max(valid, key=lambda r: (r.objective, -r.solve_ms)).is_best = True
    return rows
