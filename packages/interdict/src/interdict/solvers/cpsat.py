"""OR-Tools CP-SAT reference solver (NPHARD.md §4). THIS is what runs in production."""
from __future__ import annotations

from ortools.sat.python import cp_model

from interdict.solvers.greedy import solve_greedy
from interdict.types import Problem

WEIGHT_SCALE = 1000  # CP-SAT needs integer objectives; floats are scaled and rounded


def solve_cpsat(p: Problem, timeout_s: float = 10.0, stats: dict | None = None) -> list[str]:
    """Maximum coverage under budget k. Domains with identical dependency sets are collapsed into
    one weighted variable first (exact: they are killed together or not at all).

    `stats`, if given, receives status (OPTIMAL | FEASIBLE), objective, bound, gap_pct, n_groups.
    A FEASIBLE result hit the time limit: it is a valid plan, not a proven optimum, and callers
    must say so. The greedy plan is the warm start (hint), and a time-limited search never returns
    a worse plan than its own warm start."""
    node_set = set(p.nodes)
    groups: dict[frozenset[str], float] = {}
    for d, s in p.deps.items():
        key = frozenset(v for v in s if v in node_set)
        if key:
            groups[key] = groups.get(key, 0.0) + p.weights[d]
    if stats is not None:
        stats.update(status="OPTIMAL", objective=0.0, bound=0.0, gap_pct=0.0, n_groups=len(groups))
    if p.k <= 0 or not p.nodes or not groups:
        return []

    m = cp_model.CpModel()
    x = {v: m.NewBoolVar(f"x_{i}") for i, v in enumerate(p.nodes)}
    terms = []
    for i, (sig, w) in enumerate(groups.items()):
        y = m.NewBoolVar(f"y_{i}")
        m.Add(y <= sum(x[v] for v in sig))
        terms.append(int(round(w * WEIGHT_SCALE)) * y)
    m.Add(sum(x.values()) <= p.k)
    m.Maximize(sum(terms))
    warm = solve_greedy(p)
    for v in p.nodes:
        m.AddHint(x[v], v in warm)

    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = timeout_s
    s.parameters.num_search_workers = 8
    status = s.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"cp-sat returned {s.StatusName(status)}")
    chosen = [v for v in p.nodes if s.Value(x[v])]
    status_name = s.StatusName(status)
    if p.objective(warm) > p.objective(chosen):  # only possible when the time limit hit (FEASIBLE)
        chosen = warm
    if stats is not None:
        obj, bound = p.objective(chosen), s.BestObjectiveBound() / WEIGHT_SCALE
        stats.update(status=status_name, objective=obj, bound=bound,
                     gap_pct=round(100 * (bound - obj) / bound, 3) if bound else 0.0)
    return chosen
