"""Campaign list, detail, and the Cytoscape graph."""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query

from services.api.deps import get_conn
from services.api.models import CampaignOut, GraphOut, Page

router = APIRouter()
GRAPH_NODE_CAP = 1000
_CAMPAIGN_COLS = """id::text, label, kit_hash, domain_count, infra_count, confidence, coalesce(brands, '{}') as brands,
                    status, first_seen, published_tx"""


def campaign_or_404(c: sa.Connection, campaign_id: str):
    try:
        uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(404, f"campaign {campaign_id} not found") from None
    row = c.execute(sa.text(f"select {_CAMPAIGN_COLS} from campaigns where id = :id"), {"id": campaign_id}).mappings().first()
    if row is None:
        raise HTTPException(404, f"campaign {campaign_id} not found")
    return row


@router.get("/campaigns", response_model=Page[CampaignOut])
def list_campaigns(min_size: int = Query(0, ge=0), status: str | None = None, limit: int = Query(50, ge=1, le=500),
                   offset: int = Query(0, ge=0), c=Depends(get_conn)):
    rows = c.execute(sa.text(f"""
        select {_CAMPAIGN_COLS}, count(*) over () as total from campaigns
        where domain_count >= :min and (cast(:status as text) is null or status = :status)
        order by domain_count desc, first_seen desc limit :limit offset :offset"""),
        {"min": min_size, "status": status, "limit": limit, "offset": offset}).mappings().all()
    return {"items": [{k: v for k, v in r.items() if k != "total"} for r in rows],
            "total": rows[0]["total"] if rows else 0, "limit": limit, "offset": offset}


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: str, c=Depends(get_conn)):
    return campaign_or_404(c, campaign_id)


@router.get("/campaigns/{campaign_id}/graph", response_model=GraphOut)
def campaign_graph(campaign_id: str, c=Depends(get_conn)):
    campaign_or_404(c, campaign_id)
    rows = c.execute(sa.text("""
        select d.id as did, d.name, d.status, n.id as nid, n.kind, n.value, n.domain_count, e.weight
        from domains d
        left join graph_edges e on e.domain_id = d.id
        left join infra_nodes n on n.id = e.node_id
        where d.campaign_id = :c"""), {"c": campaign_id}).mappings().all()
    targets = {r.node_id: r.rank for r in c.execute(sa.text("""
        select t.node_id, t.rank from plan_targets t
        where t.plan_id = (select id from interdiction_plans where campaign_id = :c order by created_at desc limit 1)"""),
        {"c": campaign_id})}
    domains, infra, edges = {}, {}, []
    for r in rows:
        domains[r["did"]] = r
        if r["nid"] is not None:
            infra[r["nid"]] = r
            edges.append((r["did"], r["nid"], r["weight"]))
    truncated = len(domains) + len(infra) > GRAPH_NODE_CAP
    nodes = []
    for nid, r in infra.items():
        d = {"id": f"n:{nid}", "kind": r["kind"], "label": r["value"], "domain_count": r["domain_count"]}
        if nid in targets:
            d.update(is_target=True, target_rank=targets[nid])
        nodes.append({"data": d})
    out_edges = []
    if not truncated:
        for did, r in domains.items():
            nodes.append({"data": {"id": f"d:{did}", "kind": "domain", "label": r["name"], "status": r["status"],
                                   "weight": 1.0}})
        out_edges = [{"data": {"id": f"e:{i}", "source": f"d:{d}", "target": f"n:{n}", "weight": w}}
                     for i, (d, n, w) in enumerate(edges)]
    return {"campaign_id": campaign_id, "truncated": truncated, "node_count": len(nodes),
            "elements": {"nodes": nodes, "edges": out_edges}}
