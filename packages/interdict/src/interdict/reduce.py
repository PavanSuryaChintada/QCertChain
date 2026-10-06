"""Classical reduction before any QUBO (NPHARD.md §5): collapse -> prune -> top-C."""
from __future__ import annotations

from dataclasses import dataclass, field

from interdict.types import Problem


@dataclass
class Reduced:
    problem: Problem               # domains = group ids (weights summed), nodes = kept candidates
    groups: dict[str, list[str]]   # group id -> original domain ids
    notes: list[str] = field(default_factory=list)

    @property
    def n_variables(self) -> int:
        return len(self.problem.nodes)  # x-only QUBO: one variable per candidate node


def collapse(p: Problem, nodes: tuple[str, ...] | None = None) -> tuple[Problem, dict[str, list[str]]]:
    """Group domains with identical dependency sets (restricted to `nodes`). Domains left with no
    dependency among `nodes` cannot be killed by any takedown and are dropped from the groups."""
    keep = set(nodes if nodes is not None else p.nodes)
    by_sig: dict[frozenset[str], list[str]] = {}
    for d, s in p.deps.items():
        sig = frozenset(s & keep)
        if sig:
            by_sig.setdefault(sig, []).append(d)
    deps, weights, groups = {}, {}, {}
    for i, (sig, members) in enumerate(sorted(by_sig.items(), key=lambda kv: sorted(kv[0]))):
        gid = f"grp{i}"
        deps[gid] = sig
        weights[gid] = sum(p.weights[d] for d in members)
        groups[gid] = members
    kept = tuple(v for v in p.nodes if v in keep)
    return Problem(kept, deps, weights, p.k), groups


def _coverage(p: Problem) -> dict[str, frozenset[str]]:
    cov: dict[str, set[str]] = {v: set() for v in p.nodes}
    for g, s in p.deps.items():
        for v in s:
            if v in cov:
                cov[v].add(g)
    return {v: frozenset(c) for v, c in cov.items()}


def _prune(p: Problem) -> tuple[str, ...]:
    """Drop nodes covering nothing, and nodes whose coverage is a subset of another node's
    (equal coverage: keep the first in node order). Exact: a dominated node is never strictly better."""
    cov = _coverage(p)
    live = [v for v in p.nodes if cov[v]]
    keep = []
    for i, v in enumerate(live):
        dominated = any((cov[v] < cov[u]) or (cov[v] == cov[u] and j < i)
                        for j, u in enumerate(live) if u != v)
        if not dominated:
            keep.append(v)
    return tuple(keep)


def reduce(p: Problem, C: int = 12, max_vars: int = 24) -> Reduced:
    notes: list[str] = []
    cp, _ = collapse(p)
    nodes = _prune(cp)
    if len(nodes) < len(p.nodes):
        notes.append(f"pruned {len(p.nodes) - len(nodes)} empty or dominated nodes")
    cov = _coverage(Problem(nodes, cp.deps, cp.weights, p.k))
    ranked = sorted(nodes, key=lambda v: (-sum(cp.weights[g] for g in cov[v]), v))
    c = min(C, max_vars)
    if c < C:
        notes.append(f"lowered C from {C} to {c} to fit {max_vars} variables")
    top_set = set(ranked[:c])
    top = tuple(v for v in p.nodes if v in top_set)
    rp, groups_map = collapse(p, top)
    lost = sum(p.weights.values()) - sum(rp.weights.values())
    if lost > 0:
        notes.append(f"weight {lost:g} unreachable by the kept {len(top)} candidate nodes")
    return Reduced(rp, groups_map, notes)
