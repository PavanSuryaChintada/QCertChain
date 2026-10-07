"""Campaign snapshots (T14/T15): the campaign graph, the solver input and the budget sweep, precomputed.

Built when clustering changes a campaign, so GET /campaigns/{id}/graph is one row read and the budget slider is a
lookup. Every query here runs on a connection whose org context is set (current_org()); org-owned tables are
filtered by it explicitly, and row-level security backs that up on the API path.

Compact graph format (a 400-domain campaign is ~60 KB before gzip, vs ~210 KB as Cytoscape elements):
  domains: [[domain_id, name, status], ...]
  nodes:   [[node_id, kind, value, domain_count, targetable], ...]   targetable = ip / nameserver / registrar
  edges:   [[domain_id, node_id, weight], ...]
"""
from __future__ import annotations

import json

import sqlalchemy as sa

from interdict.types import Problem

TAKEDOWN_ROUTE = {"ip": "hosting", "nameserver": "dns", "registrar": "registrar"}  # spec D9
SWEEP_KS = range(1, 11)  # the console's budget slider: k = 1..10


def build_snapshot(c: sa.Connection, campaign_id: str) -> dict:
    rows = c.execute(sa.text("""
        select d.id as did, d.name, d.status, d.weight, n.id as nid, n.kind, n.value, n.domain_count, e.weight as ew
        from org_domains d
        left join graph_edges e on e.domain_id = d.id and e.org_id = current_org()
        left join infra_nodes n on n.id = e.node_id and n.org_id = current_org()
        where d.campaign_id = :c
        order by d.id, n.id"""), {"c": campaign_id}).mappings().all()
    domains: dict[int, list] = {}
    nodes: dict[int, list] = {}
    edges: list[list] = []
    deps: dict[str, list[int]] = {}
    weights: dict[str, float] = {}
    for r in rows:
        domains.setdefault(r["did"], [r["did"], r["name"], r["status"]])
        deps.setdefault(str(r["did"]), [])
        weights[str(r["did"])] = float(r["weight"] or 1.0)
        if r["nid"] is None:
            continue
        targetable = r["kind"] in TAKEDOWN_ROUTE
        nodes.setdefault(r["nid"], [r["nid"], r["kind"], r["value"], r["domain_count"], targetable])
        edges.append([r["did"], r["nid"], round(float(r["ew"]), 2)])
        if targetable:
            deps[str(r["did"])].append(r["nid"])
    graph = {"domains": list(domains.values()), "nodes": list(nodes.values()), "edges": edges}
    problem = {"nodes": {str(n[0]): [n[1], n[2]] for n in nodes.values() if n[4]}, "deps": deps, "weights": weights}
    payload = json.dumps(graph, separators=(",", ":"))
    c.execute(sa.text("""
        insert into campaign_snapshots (campaign_id, graph, problem, n_targetable, payload_bytes, built_at,
                                        sweep, sweep_built_at)
        values (:c, cast(:g as jsonb), cast(:p as jsonb), :n, :b, clock_timestamp(), null, null)
        on conflict (org_id, campaign_id) do update set graph = excluded.graph, problem = excluded.problem,
          n_targetable = excluded.n_targetable, payload_bytes = excluded.payload_bytes, built_at = excluded.built_at,
          sweep = null, sweep_built_at = null"""),
        {"c": campaign_id, "g": payload, "p": json.dumps(problem), "n": len(problem["nodes"]), "b": len(payload)})
    return {"graph": graph, "problem": problem}


def to_problem(problem: dict, k: int) -> tuple[Problem, dict[str, dict]]:
    nodes = problem["nodes"]
    meta = {nid: {"node_id": int(nid), "kind": kv[0], "value": kv[1]} for nid, kv in nodes.items()}
    deps = {d: frozenset(str(n) for n in ns) for d, ns in problem["deps"].items()}
    return Problem(tuple(sorted(nodes, key=int)), deps, dict(problem["weights"]), k), meta


def ranked_targets(p: Problem, targets: list[str]) -> list[tuple[str, int]]:
    """Rank by marginal kills (greedy order over the chosen set): the column sums to domains_killed."""
    out, dead, left = [], set(), list(targets)
    while left:
        best = max(left, key=lambda t: (len(p.coverage([t]) - dead), -int(t)))
        gain = p.coverage([best]) - dead
        out.append((best, len(gain)))
        dead |= gain
        left.remove(best)
    return out


def plan_summary(p: Problem, meta: dict, plan) -> dict:
    ranked = ranked_targets(p, plan.targets)
    return {"k": p.k, "backend": plan.backend, "domains_killed": len(plan.killed),
            "domains_total": plan.domains_total, "coverage_pct": plan.coverage_pct, "solve_ms": plan.solve_ms,
            "valid": plan.valid, "notes": list(plan.notes or []),
            "targets": [{"node_id": meta[t]["node_id"], "kind": meta[t]["kind"], "value": meta[t]["value"],
                         "kills": kills, "route": TAKEDOWN_ROUTE[meta[t]["kind"]]} for t, kills in ranked],
            "killed_ids": sorted(int(d) for d in plan.killed)}


def build_sweep(c: sa.Connection, campaign_id: str, problem: dict | None = None, *, max_vars: int = 24) -> list[dict]:
    """CP-SAT (the production solver) for every slider position. Stored on the snapshot."""
    from interdict.router import solve
    if problem is None:
        problem = c.execute(sa.text("""select problem from campaign_snapshots
                                       where campaign_id = :c and org_id = current_org()"""),
                            {"c": campaign_id}).scalar_one()
    n = len(problem["nodes"])
    out = []
    for k in SWEEP_KS:
        if k > n:
            break
        p, meta = to_problem(problem, k)
        out.append(plan_summary(p, meta, solve(p, backend="cpsat", timeout_s=1.0, max_vars=max_vars)))
    c.execute(sa.text("""update campaign_snapshots set sweep = cast(:s as jsonb), sweep_built_at = clock_timestamp()
                         where campaign_id = :c and org_id = current_org()"""),
              {"s": json.dumps(out), "c": campaign_id})
    return out
