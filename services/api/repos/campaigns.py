from __future__ import annotations

import uuid

import sqlalchemy as sa

from services.api.deps import Scope

_COLS = """id::text, label, kit_hash, domain_count, infra_count, confidence, coalesce(brands, '{}') as brands,
           status, first_seen, last_seen, published_tx, published_tx is not null as anchored,
           exists (select 1 from interdiction_plans p where p.campaign_id = campaigns.id
                   and p.org_id = campaigns.org_id) as has_plan"""


def get(s: Scope, campaign_id: str) -> dict | None:
    try:
        uuid.UUID(campaign_id)
    except ValueError:
        return None
    r = s.conn.execute(sa.text(f"select {_COLS} from campaigns where id = :id and org_id = :org"),
                       {"id": campaign_id, "org": s.org_id}).mappings().first()
    return dict(r) if r else None


def list_(s: Scope, *, min_size: int, status: str | None, limit: int, after: list | None) -> list[dict]:
    """Keyset on (domain_count, first_seen, id) desc; returns limit + 1 rows."""
    return [dict(r) for r in s.conn.execute(sa.text(f"""
        select {_COLS} from campaigns
        where org_id = :org and domain_count >= :min and (cast(:status as text) is null or status = :status)
          and (cast(:ad as int) is null or (domain_count, first_seen, id) <
               (cast(:ad as int), cast(:af as timestamptz), cast(:ai as uuid)))
        order by domain_count desc, first_seen desc, id desc limit :limit"""),
        {"org": s.org_id, "min": min_size, "status": status, "limit": limit + 1,
         "ad": after[0] if after else None, "af": after[1] if after else None,
         "ai": after[2] if after else None}).mappings()]


def graph_json(s: Scope, campaign_id: str) -> str | None:
    """The graph response, assembled AS TEXT by Postgres from the snapshot (one statement): a 400-domain graph is
    never decoded into Python objects and re-encoded. None: not this org's campaign, or no snapshot yet."""
    try:
        uuid.UUID(campaign_id)
    except ValueError:
        return None
    return s.conn.execute(sa.text("""
        select json_build_object(
                 'campaign_id', s.campaign_id, 'n_targetable', s.n_targetable, 'search_space_log2', s.n_targetable,
                 'domains', s.graph->'domains', 'nodes', s.graph->'nodes', 'edges', s.graph->'edges',
                 'built_at', s.built_at,
                 'targets', (select coalesce(json_agg(json_build_array(t.node_id, t.rank) order by t.rank), '[]'::json)
                               from plan_targets t
                              where t.plan_id = (select id from interdiction_plans where campaign_id = :c
                                                 and org_id = :org order by created_at desc limit 1)))::text
        from campaign_snapshots s where s.campaign_id = :c and s.org_id = :org"""),
        {"c": campaign_id, "org": s.org_id}).scalar()


def sweep_json(s: Scope, campaign_id: str) -> str | None:
    """The cached sweep response as text (one statement); None if not this org's or not computed yet."""
    try:
        uuid.UUID(campaign_id)
    except ValueError:
        return None
    return s.conn.execute(sa.text("""
        select json_build_object('campaign_id', campaign_id, 'n_targetable', n_targetable,
                                 'search_space_log2', n_targetable, 'cached', true, 'points', sweep)::text
        from campaign_snapshots where campaign_id = :c and org_id = :org and sweep is not null"""),
        {"c": campaign_id, "org": s.org_id}).scalar()


def snapshot(s: Scope, campaign_id: str) -> dict | None:
    """The precomputed graph and the latest plan's targets, in ONE statement. None if the campaign is not this
    org's (or has no snapshot yet: the caller builds it once)."""
    try:
        uuid.UUID(campaign_id)
    except ValueError:
        return None
    r = s.conn.execute(sa.text("""
        select s.graph, s.n_targetable, s.payload_bytes, s.built_at,
               (select coalesce(json_agg(json_build_array(t.node_id, t.rank) order by t.rank), '[]'::json)
                  from plan_targets t
                 where t.plan_id = (select id from interdiction_plans
                                    where campaign_id = :c and org_id = :org order by created_at desc limit 1)
               ) as targets
        from campaign_snapshots s where s.campaign_id = :c and s.org_id = :org"""),
        {"c": campaign_id, "org": s.org_id}).mappings().one_or_none()
    return dict(r) if r else None


def build_snapshot(s: Scope, campaign_id: str) -> None:
    from services.graph.snapshot import build_snapshot as build
    build(s.conn, campaign_id)


def sweep(s: Scope, campaign_id: str) -> dict | None:
    """The budget sweep k = 1..10, computed once and cached on the snapshot."""
    try:
        uuid.UUID(campaign_id)
    except ValueError:
        return None
    r = s.conn.execute(sa.text("""select sweep, problem, n_targetable, sweep_built_at from campaign_snapshots
                                  where campaign_id = :c and org_id = :org"""),
                       {"c": campaign_id, "org": s.org_id}).mappings().one_or_none()
    if r is None:
        return None
    out = dict(r)
    if out["sweep"] is None:
        from services.config import SETTINGS
        from services.graph.snapshot import build_sweep
        out["sweep"] = build_sweep(s.conn, campaign_id, out["problem"], max_vars=SETTINGS.max_qubo_variables)
        out["cached"] = False
    else:
        out["cached"] = True
    return out
