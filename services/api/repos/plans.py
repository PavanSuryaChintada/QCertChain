from __future__ import annotations

import json
import uuid

import sqlalchemy as sa

from services.api import repo
from services.api.deps import Scope


def problem_rows(s: Scope, campaign_id: str, kinds: list[str]) -> list[dict]:
    """Takedownable infrastructure of the campaign's domains (this org's graph only)."""
    return [dict(r) for r in s.conn.execute(sa.text("""
        select d.id as did, d.weight as w, n.id as nid, n.kind, n.value
        from org_domains d
        left join graph_edges e on e.domain_id = d.id and e.org_id = :org
        left join infra_nodes n on n.id = e.node_id and n.kind = any(:kinds)
        where d.campaign_id = :c"""), {"c": campaign_id, "org": s.org_id, "kinds": kinds}).mappings()]


def insert_plan(s: Scope, campaign_id: str, k: int, plan, targets: list[dict]) -> str:
    plan_id = str(uuid.uuid4())
    s.conn.execute(sa.text("""
        insert into interdiction_plans (id, org_id, campaign_id, budget_k, backend, fell_back, fallback_from, objective,
            domains_killed, domains_total, coverage_pct, n_variables, qubit_count, solve_ms, valid,
            killed_domain_ids, notes)
        values (:id, :org, :c, :k, :b, :fb, :ff, :obj, :killed, :total, :cov, :nv, :q, :ms, :valid, :kids, :notes)"""),
        {"id": plan_id, "org": s.org_id, "c": campaign_id, "k": k, "b": plan.backend, "fb": plan.fell_back,
         "ff": plan.fallback_from, "obj": plan.objective, "killed": len(plan.killed), "total": plan.domains_total,
         "cov": plan.coverage_pct, "nv": plan.n_variables, "q": plan.qubit_count, "ms": plan.solve_ms,
         "valid": plan.valid, "kids": sorted(int(d) for d in plan.killed), "notes": plan.notes})
    s.conn.execute(sa.text("""
        insert into plan_targets (org_id, plan_id, node_id, rank, kills, takedown_route)
        select :org, :p, x.n, x.r, x.k, x.route from jsonb_to_recordset(cast(:rows as jsonb))
               as x(n bigint, r smallint, k int, route text)"""),
        {"org": s.org_id, "p": plan_id, "rows": json.dumps(targets)})
    return plan_id


def get_plan(s: Scope, plan_id: str) -> tuple[dict, list[dict]] | None:
    try:
        uuid.UUID(plan_id)
    except ValueError:
        return None
    p = s.conn.execute(sa.text("""select *, id::text as pid, campaign_id::text as cid from interdiction_plans
                                  where id = :id and org_id = :org"""),
                       {"id": plan_id, "org": s.org_id}).mappings().one_or_none()
    if p is None:
        return None
    targets = s.conn.execute(sa.text("""
        select t.rank, t.node_id, n.kind, n.value, t.kills, t.takedown_route from plan_targets t
        join infra_nodes n on n.id = t.node_id where t.plan_id = :id order by t.rank"""),
        {"id": plan_id}).mappings().all()
    return dict(p), [dict(t) for t in targets]


def insert_benchmarks(s: Scope, plan_id: str, rows: list[dict]) -> None:
    s.conn.execute(sa.text("""
        insert into benchmarks (org_id, plan_id, backend, objective, domains_killed, coverage_pct, solve_ms, valid,
                                n_variables, qubit_count, is_best, targets, error)
        select :org, :p, x.backend, x.obj, x.killed, x.cov, x.ms, x.valid, x.nv, x.q, x.best, x.targets, x.error
        from jsonb_to_recordset(cast(:rows as jsonb)) as x(backend text, obj real, killed int, cov real, ms int,
             valid boolean, nv smallint, q smallint, best boolean, targets jsonb, error text)"""),
        {"org": s.org_id, "p": plan_id, "rows": json.dumps(rows)})


def log(s: Scope, channel: str, message: str, context: dict | None = None) -> None:
    repo.log(s.conn, channel, message, context=context)
