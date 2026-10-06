"""Interdiction plans and the honest benchmark (NPHARD.md, API_CONTRACT §4)."""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException

from interdict.benchmark import GREEDY_GUARANTEE, benchmark
from interdict.router import solve
from interdict.types import Problem
from services.api import repo
from services.api.deps import get_conn
from services.api.models import BenchmarkOut, InterdictRequest, PlanOut
from services.api.routes.campaigns import campaign_or_404
from services.config import SETTINGS
from services.graph.build import TAKEDOWN_ROUTE

router = APIRouter()
QUANTUM_FRAMING = ("Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; "
                   "the same formulation runs on QAOA. Quantum is not in the critical path.")


def build_problem(c: sa.Connection, campaign_id: str, k: int) -> tuple[Problem, dict[str, dict]]:
    """Nodes = takedownable infrastructure (ip / nameserver / registrar) of the campaign's domains."""
    rows = c.execute(sa.text("""
        select d.id as did, coalesce(d.weight, 1.0) as w, n.id as nid, n.kind, n.value
        from domains d
        left join graph_edges e on e.domain_id = d.id
        left join infra_nodes n on n.id = e.node_id and n.kind = any(:kinds)
        where d.campaign_id = :c"""), {"c": campaign_id, "kinds": list(TAKEDOWN_ROUTE)}).mappings().all()
    deps: dict[str, set[str]] = {}
    weights: dict[str, float] = {}
    meta: dict[str, dict] = {}
    for r in rows:
        d = str(r["did"])
        deps.setdefault(d, set())
        weights[d] = float(r["w"])
        if r["nid"] is not None:
            n = str(r["nid"])
            deps[d].add(n)
            meta[n] = {"node_id": r["nid"], "kind": r["kind"], "value": r["value"]}
    return Problem(tuple(sorted(meta, key=int)), {d: frozenset(s) for d, s in deps.items()}, weights, k), meta


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


def _plan_out(c: sa.Connection, plan_id: str) -> dict:
    p = c.execute(sa.text("select *, id::text as pid, campaign_id::text as cid from interdiction_plans where id = :id"),
                  {"id": plan_id}).mappings().one_or_none()
    if p is None:
        raise HTTPException(404, f"plan {plan_id} not found")
    targets = c.execute(sa.text("""
        select t.rank, t.node_id, n.kind, n.value, t.kills, t.takedown_route from plan_targets t
        join infra_nodes n on n.id = t.node_id where t.plan_id = :id order by t.rank"""), {"id": plan_id}).mappings().all()
    return {"plan_id": p["pid"], "campaign_id": p["cid"], "budget_k": p["budget_k"], "backend": p["backend"],
            "fell_back": p["fell_back"], "fallback_from": p["fallback_from"], "objective": p["objective"],
            "domains_killed": p["domains_killed"], "domains_total": p["domains_total"], "coverage_pct": p["coverage_pct"],
            "n_variables": p["n_variables"], "qubit_count": p["qubit_count"], "solve_ms": p["solve_ms"],
            "valid": p["valid"], "targets": [dict(t) for t in targets],
            "killed_domain_ids": p["killed_domain_ids"] or [], "notes": p["notes"] or []}


@router.post("/campaigns/{campaign_id}/interdict", response_model=PlanOut)
def interdict(campaign_id: str, body: InterdictRequest, c=Depends(get_conn)):
    campaign_or_404(c, campaign_id)
    p, meta = build_problem(c, campaign_id, body.k)
    if not p.nodes:
        raise HTTPException(409, "No shared infrastructure — nothing to interdict.")
    if body.k > len(p.nodes):
        raise HTTPException(422, f"k={body.k} exceeds the {len(p.nodes)} takedown candidates (max {len(p.nodes)})")
    plan = solve(p, backend=body.backend, timeout_s=body.timeout_s, max_vars=SETTINGS.max_qubo_variables)
    ranked = ranked_targets(p, plan.targets)
    plan_id = str(uuid.uuid4())
    c.execute(sa.text("""
        insert into interdiction_plans (id, campaign_id, budget_k, backend, fell_back, fallback_from, objective,
            domains_killed, domains_total, coverage_pct, n_variables, qubit_count, solve_ms, valid,
            killed_domain_ids, notes)
        values (:id, :c, :k, :b, :fb, :ff, :obj, :killed, :total, :cov, :nv, :q, :ms, :valid, :kids, :notes)"""),
        {"id": plan_id, "c": campaign_id, "k": body.k, "b": plan.backend, "fb": plan.fell_back,
         "ff": plan.fallback_from, "obj": plan.objective, "killed": len(plan.killed), "total": plan.domains_total,
         "cov": plan.coverage_pct, "nv": plan.n_variables, "q": plan.qubit_count, "ms": plan.solve_ms,
         "valid": plan.valid, "kids": sorted(int(d) for d in plan.killed), "notes": plan.notes})
    c.execute(sa.text("""
        insert into plan_targets (plan_id, node_id, rank, kills, takedown_route)
        select :p, x.n, x.r, x.k, x.route from jsonb_to_recordset(cast(:rows as jsonb))
               as x(n bigint, r smallint, k int, route text)"""),
        {"p": plan_id, "rows": json.dumps([{"n": meta[t]["node_id"], "r": i + 1, "k": kills,
                                            "route": TAKEDOWN_ROUTE[meta[t]["kind"]]}
                                           for i, (t, kills) in enumerate(ranked)])})
    msg = f"plan {plan_id[:4]} solved · {plan.backend} · {plan.solve_ms}ms · {len(plan.killed)}/{plan.domains_total}"
    if plan.fell_back:
        msg += f" · {plan.fallback_from} → {plan.backend}"
    repo.log(c, "interdict", msg, context={"plan_id": plan_id})
    return _plan_out(c, plan_id)


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: str, c=Depends(get_conn)):
    try:
        uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(404, f"plan {plan_id} not found") from None
    return _plan_out(c, plan_id)


@router.post("/plans/{plan_id}/benchmark", response_model=BenchmarkOut)
def plan_benchmark(plan_id: str, c=Depends(get_conn)):
    plan = get_plan(plan_id, c)
    p, _ = build_problem(c, plan["campaign_id"], plan["budget_k"])
    rows = benchmark(p, max_vars=SETTINGS.max_qubo_variables)
    c.execute(sa.text("""
        insert into benchmarks (plan_id, backend, objective, domains_killed, coverage_pct, solve_ms, valid, n_variables,
                                qubit_count, is_best, targets, error)
        select :p, x.backend, x.obj, x.killed, x.cov, x.ms, x.valid, x.nv, x.q, x.best, x.targets, x.error
        from jsonb_to_recordset(cast(:rows as jsonb)) as x(backend text, obj real, killed int, cov real, ms int,
             valid boolean, nv smallint, q smallint, best boolean, targets jsonb, error text)"""),
        {"p": plan_id, "rows": json.dumps([{"backend": r.backend, "obj": r.objective, "killed": r.domains_killed,
                                            "cov": r.coverage_pct, "ms": r.solve_ms, "valid": r.valid,
                                            "nv": r.n_variables, "q": r.qubit_count, "best": r.is_best,
                                            "targets": r.targets, "error": r.error} for r in rows])})
    repo.log(c, "interdict", f"benchmark {plan_id[:4]}: " + " · ".join(
        f"{r.backend} {r.domains_killed}/{r.domains_total} {r.solve_ms}ms" if r.valid else f"{r.backend} failed"
        for r in rows), context={"plan_id": plan_id})
    return {"plan_id": plan_id, "n_variables": rows[0].n_variables if rows else 0,
            "rows": [{"backend": r.backend, "objective": r.objective, "domains_killed": r.domains_killed,
                      "coverage_pct": r.coverage_pct, "solve_ms": r.solve_ms, "valid": r.valid,
                      "qubit_count": r.qubit_count, "n_variables": r.n_variables, "is_best": r.is_best,
                      "error": r.error, "notes": r.notes} for r in rows],
            "note": f"{QUANTUM_FRAMING} Every backend is reported, losses included; {GREEDY_GUARANTEE}."}
