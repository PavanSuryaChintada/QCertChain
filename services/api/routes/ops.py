"""Metrics, the ops log, and demo seeding."""
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query

from services.api.deps import get_conn, get_evidence_dir, get_redis, get_signing_key
from services.api.models import CampaignOut, Metrics, OpsLogItem, Page, SeedRequest
from services.api.routes.campaigns import campaign_or_404
from services.api.routes.stream import read_state
from services.api.seed import seed_campaign

router = APIRouter()
CHANNELS = ("stream", "triage", "confirm", "enrich", "graph", "interdict", "evidence", "ledger", "email", "system")


@router.get("/metrics", response_model=Metrics)
async def metrics(c=Depends(get_conn), r=Depends(get_redis)):
    m = c.execute(sa.text("""
        select (select count(*) from campaigns where status = 'active') as campaigns_active,
               (select count(*) from domains where status = 'confirmed') as domains_confirmed,
               (select count(*) from domains where status = 'candidate') as domains_candidate,
               (select count(*) from interdiction_plans where created_at > now() - interval '1 day') as plans_today,
               (select count(*) from evidence_bundles where created_at > now() - interval '1 day') as bundles_today,
               (select count(*) from anchor_queue where not done) as anchor_queue_depth""")).mappings().one()
    return {**m, "certs_per_sec": (await read_state(r)).certs_per_sec}  # 0 when the heartbeat is stale


@router.get("/ops/log", response_model=Page[OpsLogItem])
def ops_log(since: datetime | None = None, channel: str | None = Query(None, enum=list(CHANNELS)),
            limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), c=Depends(get_conn)):
    rows = c.execute(sa.text("""
        select id, at, channel, severity, message, context, count(*) over () as total from ops_log
        where (cast(:since as timestamptz) is null or at > :since) and (cast(:ch as text) is null or channel = :ch)
        order by id desc limit :limit offset :offset"""),
        {"since": since, "ch": channel, "limit": limit, "offset": offset}).mappings().all()
    return {"items": [{k: v for k, v in x.items() if k != "total"} for x in rows],
            "total": rows[0]["total"] if rows else 0, "limit": limit, "offset": offset}


@router.post("/seed/campaign", response_model=CampaignOut)
def seed(body: SeedRequest, c=Depends(get_conn), evidence_dir=Depends(get_evidence_dir), key=Depends(get_signing_key)):
    """Synthetic, labelled source='seed' on every row; reserved .example names only (see services/api/seed.py)."""
    cid = seed_campaign(c, label=body.label, domains=body.domains, ips=body.ips, asns=body.asns,
                        nameservers=body.nameservers, registrars=body.registrars, brands=body.brands,
                        evidence_dir=evidence_dir, signing_key_hex=key)
    return campaign_or_404(c, cid)
