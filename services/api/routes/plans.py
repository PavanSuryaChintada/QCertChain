"""Interdiction plans and the honest benchmark (NPHARD.md, API_CONTRACT §4)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from interdict.benchmark import GREEDY_GUARANTEE, benchmark
from interdict.router import solve
from interdict.types import Problem
from services.api.deps import Scope, get_scope
from services.api.models import BenchmarkOut, InterdictRequest, PlanOut
from services.api.repos import campaigns as repo_campaigns
from services.api.repos import plans as repo_plans
from services.api.routes.campaigns import campaign_or_404
from services.config import SETTINGS
from services.graph.snapshot import plan_summary, to_problem

router = APIRouter()
QUANTUM_FRAMING = ("Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; "
                   "the same formulation runs on QAOA. Quantum is not in the critical path.")


def build_problem(s: Scope, campaign_id: str, k: int) -> tuple[Problem, dict[str, dict], list | None]:
    """Nodes = takedownable infrastructure (ip / nameserver / registrar) of the campaign's domains, read from the
    precomputed snapshot. Returns (problem, node meta, cached CP-SAT sweep or None)."""
    snap = repo_plans.problem(s, campaign_id)
    if snap is None:
        campaign_or_404(s, campaign_id)
        repo_campaigns.build_snapshot(s, campaign_id)
        snap = repo_plans.problem(s, campaign_id)
    p, meta = to_problem(snap["problem"], k)
    return p, meta, snap["sweep"]


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
    p, meta, sweep = build_problem(s, campaign_id, body.k)
    if not p.nodes:
        raise HTTPException(409, "No shared infrastructure — nothing to interdict.")
    if body.k > len(p.nodes):
        raise HTTPException(422, f"k={body.k} exceeds the {len(p.nodes)} takedown candidates (max {len(p.nodes)})")
    cached = next((x for x in (sweep or []) if x["k"] == body.k), None) if body.backend == "cpsat" else None
    if cached is not None:
        # The production solver's answer for this k was computed when the snapshot was built. solve_ms is the time
        # measured THEN, and the notes say so: nothing is re-timed or invented.
        out = {**cached, "fell_back": False, "fallback_from": None, "n_variables": len(p.nodes), "qubit_count": None,
               "objective": float(cached["domains_killed"]), "killed_domain_ids": cached["killed_ids"],
               "notes": [*cached["notes"], "cached result of the precomputed CP-SAT budget sweep"]}
        targets = cached["targets"]
    else:
        plan = solve(p, backend=body.backend, timeout_s=body.timeout_s, max_vars=SETTINGS.max_qubo_variables)
        summ = plan_summary(p, meta, plan)
        out = {**summ, "fell_back": plan.fell_back, "fallback_from": plan.fallback_from,
               "n_variables": plan.n_variables, "qubit_count": plan.qubit_count, "objective": plan.objective,
               "killed_domain_ids": summ["killed_ids"]}
        targets = summ["targets"]
    plan_id = str(uuid.uuid4())
    msg = (f"plan {plan_id[:4]} solved · {out['backend']} · {out['solve_ms']}ms · "
           f"{out['domains_killed']}/{out['domains_total']}")
    if out["fell_back"]:
        msg += f" · {out['fallback_from']} → {out['backend']}"
    repo_plans.insert_plan(s, plan_id, campaign_id, body.k, out, [
        {"n": t["node_id"], "r": i + 1, "k": t["kills"], "route": t["route"]} for i, t in enumerate(targets)], msg)
    return {"plan_id": plan_id, "campaign_id": campaign_id, "budget_k": body.k, "backend": out["backend"],
            "fell_back": out["fell_back"], "fallback_from": out["fallback_from"], "objective": out["objective"],
            "domains_killed": out["domains_killed"], "domains_total": out["domains_total"],
            "coverage_pct": out["coverage_pct"], "n_variables": out["n_variables"], "qubit_count": out["qubit_count"],
            "solve_ms": out["solve_ms"], "valid": out["valid"],
            "targets": [{"rank": i + 1, "node_id": t["node_id"], "kind": t["kind"], "value": t["value"],
                         "kills": t["kills"], "takedown_route": t["route"]} for i, t in enumerate(targets)],
            "killed_domain_ids": out["killed_domain_ids"], "notes": out["notes"]}


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: str, s: Scope = Depends(get_scope)):
    return _plan_out(s, plan_id)


@router.post("/plans/{plan_id}/benchmark", response_model=BenchmarkOut)
def plan_benchmark(plan_id: str, s: Scope = Depends(get_scope)):
    plan = _plan_out(s, plan_id)
    p, _, _ = build_problem(s, plan["campaign_id"], plan["budget_k"])
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
