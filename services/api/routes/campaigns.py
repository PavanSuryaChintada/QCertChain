"""Campaign list, detail, and the Cytoscape graph. Org-scoped: another org's campaign is a 404."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from services.api import cursor
from services.api.deps import Scope, get_scope
from services.api.models import CampaignOut, GraphOut, Page, SweepOut
from services.api.repos import campaigns as repo_campaigns

router = APIRouter()


def campaign_or_404(s: Scope, campaign_id: str) -> dict:
    row = repo_campaigns.get(s, campaign_id)
    if row is None:
        raise HTTPException(404, f"campaign {campaign_id} not found")
    return row


@router.get("/campaigns", response_model=Page[CampaignOut])
def list_campaigns(min_size: int = Query(0, ge=0), status: str | None = None, limit: int = cursor.LimitQ,
                   cursor_: str | None = Query(None, alias="cursor", max_length=512), s: Scope = Depends(get_scope)):
    rows = repo_campaigns.list_(s, min_size=min_size, status=status, limit=limit, after=cursor.decode(cursor_, 3))
    return cursor.page(rows, limit, lambda r: [r["domain_count"], r["first_seen"], r["id"]])


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: str, s: Scope = Depends(get_scope)):
    return campaign_or_404(s, campaign_id)


@router.get("/campaigns/{campaign_id}/graph", response_model=GraphOut)
def campaign_graph(campaign_id: str, s: Scope = Depends(get_scope)):
    """A read of the precomputed snapshot, returned as Postgres-built JSON (one statement). GraphOut documents the
    shape. Built once here if clustering predates snapshots."""
    body = repo_campaigns.graph_json(s, campaign_id)
    if body is None:
        campaign_or_404(s, campaign_id)
        repo_campaigns.build_snapshot(s, campaign_id)
        body = repo_campaigns.graph_json(s, campaign_id)
    return Response(body, media_type="application/json")


@router.get("/campaigns/{campaign_id}/sweep", response_model=SweepOut)
def campaign_sweep(campaign_id: str, s: Scope = Depends(get_scope)):
    """Every budget position, solved by CP-SAT once and cached: the console's k slider never waits on a solver."""
    body = repo_campaigns.sweep_json(s, campaign_id)
    if body is not None:
        return Response(body, media_type="application/json")
    sw = repo_campaigns.sweep(s, campaign_id)
    if sw is None:
        campaign_or_404(s, campaign_id)
        repo_campaigns.build_snapshot(s, campaign_id)
        sw = repo_campaigns.sweep(s, campaign_id)
    return {"campaign_id": campaign_id, "n_targetable": sw["n_targetable"], "search_space_log2": sw["n_targetable"],
            "cached": sw["cached"], "points": sw["sweep"]}
