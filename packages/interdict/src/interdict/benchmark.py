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
            msg = str(e) if str(e).startswith("skipped") else f"{type(e).__name__}: {e}"
            rows.append(BenchmarkRow(b, 0.0, 0, total, 0.0, 0, False, [], n_vars, None, error=msg))
    valid = [r for r in rows if r.valid]
    if valid:
        max(valid, key=lambda r: (r.objective, -r.solve_ms)).is_best = True
    return rows


def formulation(p: Problem, max_vars: int = 24, with_circuit: bool = True) -> dict:
    """What the QUBO / QAOA formulation of this problem actually is, for the console's formulation panel:
    the classical reduction (what it kept and what it discarded), QUBO size, qubits, and the transpiled QAOA
    circuit depth (None without Qiskit). Nothing here is a speed claim."""
    from interdict.reduce import collapse
    from interdict.solvers.qaoa import P_DEPTH, SHOTS, WARM_EPS
    red = reduce(p, max_vars=max_vars)
    groups, _ = collapse(p)
    kept = len(red.problem.nodes)
    out = {
        "qubo_variables": red.n_variables,
        "qubit_count": red.n_variables,
        "circuit_depth": None,
        "p_layers": P_DEPTH,
        "shots": SHOTS,
        "warm_start": f"initial state biased toward the greedy plan (Ry, epsilon = {WARM_EPS})",
        "reduction": {
            "original_nodes": len(p.nodes), "original_domains": len(p.deps),
            "collapsed_groups": len(groups.deps), "kept_nodes": kept, "pruned_nodes": len(p.nodes) - kept,
            "unreachable_weight": round(sum(p.weights.values()) - sum(red.problem.weights.values()), 6),
            "notes": list(red.notes),
        },
    }
    if with_circuit and red.n_variables:
        try:
            from qiskit import transpile
            from qiskit.circuit.library import QAOAAnsatz
        except ImportError:  # Qiskit absent: the system runs without it; depth is simply not reported
            return out
        from interdict.qubo import build_qubo
        from interdict.solvers.qaoa import qubo_to_ising
        Q, const, names = build_qubo(red.problem)
        H, _ = qubo_to_ising(Q, const, len(names))
        ansatz = QAOAAnsatz(cost_operator=H, reps=P_DEPTH)
        out["circuit_depth"] = transpile(ansatz, basis_gates=["cx", "rz", "sx", "x"], optimization_level=1).depth()
    return out
