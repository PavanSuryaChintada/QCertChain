"""Interdiction plans and the honest benchmark (NPHARD.md, API_CONTRACT §4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from interdict.benchmark import GREEDY_GUARANTEE, benchmark
from interdict.router import solve
from interdict.types import Problem
from services.api.deps import Scope, get_scope
from services.api.models import BenchmarkOut, InterdictRequest, PlanOut
from services.api.repos import plans as repo_plans
from services.api.routes.campaigns import campaign_or_404
from services.config import SETTINGS
from services.graph.build import TAKEDOWN_ROUTE

router = APIRouter()
QUANTUM_FRAMING = ("Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; "
                   "the same formulation runs on QAOA. Quantum is not in the critical path.")


def build_problem(s: Scope, campaign_id: str, k: int) -> tuple[Problem, dict[str, dict]]:
    """Nodes = takedownable infrastructure (ip / nameserver / registrar) of the campaign's domains."""
    rows = repo_plans.problem_rows(s, campaign_id, list(TAKEDOWN_ROUTE))
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


def _plan_out(s: Scope, plan_id: str) -> dict:
    got = repo_plans.get_plan(s, plan_id)
    if got is None:
        raise HTTPException(404, f"plan {plan_id} not found")
    p, targets = got
    return {"plan_id": p["pid"], "campaign_id": p["cid"], "budget_k": p["budget_k"], "backend": p["backend"],
            "fell_back": p["fell_back"], "fallback_from": p["fallback_from"], "objective": p["objective"],
            "domains_killed": p["domains_killed"], "domains_total": p["domains_total"], "coverage_pct": p["coverage_pct"],
            "n_variables": p["n_variables"], "qubit_count": p["qubit_count"], "solve_ms": p["solve_ms"],
            "valid": p["valid"], "targets": [dict(t) for t in targets],
            "killed_domain_ids": p["killed_domain_ids"] or [], "notes": p["notes"] or []}


@router.post("/campaigns/{campaign_id}/interdict", response_model=PlanOut)
def interdict(campaign_id: str, body: InterdictRequest, s: Scope = Depends(get_scope)):
    campaign_or_404(s, campaign_id)
    p, meta = build_problem(s, campaign_id, body.k)
    if not p.nodes:
        raise HTTPException(409, "No shared infrastructure — nothing to interdict.")
    if body.k > len(p.nodes):
        raise HTTPException(422, f"k={body.k} exceeds the {len(p.nodes)} takedown candidates (max {len(p.nodes)})")
    plan = solve(p, backend=body.backend, timeout_s=body.timeout_s, max_vars=SETTINGS.max_qubo_variables)
    ranked = ranked_targets(p, plan.targets)
    plan_id = repo_plans.insert_plan(s, campaign_id, body.k, plan, [
        {"n": meta[t]["node_id"], "r": i + 1, "k": kills, "route": TAKEDOWN_ROUTE[meta[t]["kind"]]}
        for i, (t, kills) in enumerate(ranked)])
    msg = f"plan {plan_id[:4]} solved · {plan.backend} · {plan.solve_ms}ms · {len(plan.killed)}/{plan.domains_total}"
    if plan.fell_back:
        msg += f" · {plan.fallback_from} → {plan.backend}"
    repo_plans.log(s, "interdict", msg, context={"plan_id": plan_id})
    return _plan_out(s, plan_id)


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: str, s: Scope = Depends(get_scope)):
    return _plan_out(s, plan_id)


@router.post("/plans/{plan_id}/benchmark", response_model=BenchmarkOut)
def plan_benchmark(plan_id: str, s: Scope = Depends(get_scope)):
    plan = _plan_out(s, plan_id)
    p, _ = build_problem(s, plan["campaign_id"], plan["budget_k"])
    rows = benchmark(p, max_vars=SETTINGS.max_qubo_variables)
    repo_plans.insert_benchmarks(s, plan_id, [
        {"backend": r.backend, "obj": r.objective, "killed": r.domains_killed, "cov": r.coverage_pct,
         "ms": r.solve_ms, "valid": r.valid, "nv": r.n_variables, "q": r.qubit_count, "best": r.is_best,
         "targets": r.targets, "error": r.error} for r in rows])
    repo_plans.log(s, "interdict", f"benchmark {plan_id[:4]}: " + " · ".join(
        f"{r.backend} {r.domains_killed}/{r.domains_total} {r.solve_ms}ms" if r.valid else f"{r.backend} failed"
        for r in rows), context={"plan_id": plan_id})
    return {"plan_id": plan_id, "n_variables": rows[0].n_variables if rows else 0,
            "rows": [{"backend": r.backend, "objective": r.objective, "domains_killed": r.domains_killed,
                      "coverage_pct": r.coverage_pct, "solve_ms": r.solve_ms, "valid": r.valid,
                      "qubit_count": r.qubit_count, "n_variables": r.n_variables, "is_best": r.is_best,
                      "error": r.error, "notes": r.notes} for r in rows],
            "note": f"{QUANTUM_FRAMING} Every backend is reported, losses included; {GREEDY_GUARANTEE}."}
