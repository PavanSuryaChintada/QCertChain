"""Campaign list, detail, and the Cytoscape graph. Org-scoped: another org's campaign is a 404."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from services.api.deps import Scope, get_scope
from services.api.models import CampaignOut, GraphOut, Page
from services.api.repos import campaigns as repo_campaigns

router = APIRouter()
GRAPH_NODE_CAP = 1000


def campaign_or_404(s: Scope, campaign_id: str) -> dict:
    row = repo_campaigns.get(s, campaign_id)
    if row is None:
        raise HTTPException(404, f"campaign {campaign_id} not found")
    return row


@router.get("/campaigns", response_model=Page[CampaignOut])
def list_campaigns(min_size: int = Query(0, ge=0), status: str | None = None, limit: int = Query(50, ge=1, le=500),
                   offset: int = Query(0, ge=0), s: Scope = Depends(get_scope)):
    rows = repo_campaigns.list_(s, min_size=min_size, status=status, limit=limit, offset=offset)
    return {"items": [{k: v for k, v in r.items() if k != "total"} for r in rows],
            "total": rows[0]["total"] if rows else 0, "limit": limit, "offset": offset}


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: str, s: Scope = Depends(get_scope)):
    return campaign_or_404(s, campaign_id)


@router.get("/campaigns/{campaign_id}/graph", response_model=GraphOut)
def campaign_graph(campaign_id: str, s: Scope = Depends(get_scope)):
    campaign_or_404(s, campaign_id)
    rows = repo_campaigns.graph_rows(s, campaign_id)
    targets = repo_campaigns.latest_plan_targets(s, campaign_id)
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
