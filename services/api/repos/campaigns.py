from __future__ import annotations

import uuid

import sqlalchemy as sa

from services.api.deps import Scope

_COLS = """id::text, label, kit_hash, domain_count, infra_count, confidence, coalesce(brands, '{}') as brands,
           status, first_seen, published_tx"""


def get(s: Scope, campaign_id: str) -> dict | None:
    try:
        uuid.UUID(campaign_id)
    except ValueError:
        return None
    r = s.conn.execute(sa.text(f"select {_COLS} from campaigns where id = :id and org_id = :org"),
                       {"id": campaign_id, "org": s.org_id}).mappings().first()
    return dict(r) if r else None


def list_(s: Scope, *, min_size: int, status: str | None, limit: int, offset: int) -> list[dict]:
    return [dict(r) for r in s.conn.execute(sa.text(f"""
        select {_COLS}, count(*) over () as total from campaigns
        where org_id = :org and domain_count >= :min and (cast(:status as text) is null or status = :status)
        order by domain_count desc, first_seen desc limit :limit offset :offset"""),
        {"org": s.org_id, "min": min_size, "status": status, "limit": limit, "offset": offset}).mappings()]


def graph_rows(s: Scope, campaign_id: str) -> list[dict]:
    return [dict(r) for r in s.conn.execute(sa.text("""
        select d.id as did, d.name, d.status, n.id as nid, n.kind, n.value, n.domain_count, e.weight
        from org_domains d
        left join graph_edges e on e.domain_id = d.id and e.org_id = :org
        left join infra_nodes n on n.id = e.node_id
        where d.campaign_id = :c"""), {"c": campaign_id, "org": s.org_id}).mappings()]


def latest_plan_targets(s: Scope, campaign_id: str) -> dict[int, int]:
    return {r.node_id: r.rank for r in s.conn.execute(sa.text("""
        select t.node_id, t.rank from plan_targets t
        where t.plan_id = (select id from interdiction_plans where campaign_id = :c and org_id = :org
                           order by created_at desc limit 1)"""), {"c": campaign_id, "org": s.org_id})}
