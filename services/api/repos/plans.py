from __future__ import annotations

import json
import uuid

import sqlalchemy as sa

from services.api import repo
from services.api.deps import Scope


def problem(s: Scope, campaign_id: str) -> dict | None:
    """Solver input + cached sweep from the campaign snapshot, in one statement. None: not this org's campaign
    (or no snapshot yet)."""
    try:
        uuid.UUID(campaign_id)
    except ValueError:
        return None
    r = s.conn.execute(sa.text("""select problem, sweep from campaign_snapshots
                                  where campaign_id = :c and org_id = :org"""),
                       {"c": campaign_id, "org": s.org_id}).mappings().one_or_none()
    return dict(r) if r else None


def insert_plan(s: Scope, plan_id: str, campaign_id: str, k: int, plan: dict, targets: list[dict], message: str) -> None:
    """Plan, its ranked targets and the ops-log line in ONE statement (data-modifying CTEs)."""
    s.conn.execute(sa.text("""
        with p as (
          insert into interdiction_plans (id, org_id, campaign_id, budget_k, backend, fell_back, fallback_from,
              objective, domains_killed, domains_total, coverage_pct, n_variables, qubit_count, solve_ms, valid,
              killed_domain_ids, notes)
          values (:id, :org, :c, :k, :b, :fb, :ff, :obj, :killed, :total, :cov, :nv, :q, :ms, :valid, :kids, :notes)
          returning id),
        t as (
          insert into plan_targets (org_id, plan_id, node_id, rank, kills, takedown_route)
          select :org, (select id from p), x.n, x.r, x.k, x.route
          from jsonb_to_recordset(cast(:rows as jsonb)) as x(n bigint, r smallint, k int, route text)
          returning 1)
        insert into ops_log (org_id, channel, message, context)
        select :org, 'interdict', :msg, cast(:ctx as jsonb) from p"""),
        {"id": plan_id, "org": s.org_id, "c": campaign_id, "k": k, "b": plan["backend"], "fb": plan["fell_back"],
         "ff": plan["fallback_from"], "obj": plan["objective"], "killed": plan["domains_killed"],
         "total": plan["domains_total"], "cov": plan["coverage_pct"], "nv": plan["n_variables"],
         "q": plan["qubit_count"], "ms": plan["solve_ms"], "valid": plan["valid"], "kids": plan["killed_domain_ids"],
         "notes": plan["notes"], "rows": json.dumps(targets), "msg": message,
         "ctx": json.dumps({"plan_id": plan_id})})


def get_plan(s: Scope, plan_id: str) -> tuple[dict, list[dict]] | None:
    """The plan and its ranked targets in one statement."""
    try:
        uuid.UUID(plan_id)
    except ValueError:
        return None
    p = s.conn.execute(sa.text("""
        select pl.*, pl.id::text as pid, pl.campaign_id::text as cid,
               (select coalesce(json_agg(json_build_object('rank', t.rank, 'node_id', t.node_id, 'kind', n.kind,
                                         'value', n.value, 'kills', t.kills, 'takedown_route', t.takedown_route)
                                         order by t.rank), '[]'::json)
                  from plan_targets t join infra_nodes n on n.id = t.node_id
                 where t.plan_id = pl.id and t.org_id = :org) as targets
        from interdiction_plans pl where pl.id = :id and pl.org_id = :org"""),
        {"id": plan_id, "org": s.org_id}).mappings().one_or_none()
    if p is None:
        return None
    return dict(p), list(p["targets"])


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
