"""Metrics, the ops log, and demo seeding."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from services.api.deps import Scope, get_redis, get_scope
from services.api.models import Metrics, OpsLogItem, Page
from services.api.repos import ops as repo_ops
from services.api.routes.stream import read_state

router = APIRouter()
CHANNELS = ("stream", "triage", "confirm", "enrich", "graph", "interdict", "evidence", "ledger", "email", "system")


@router.get("/metrics", response_model=Metrics)
async def metrics(s: Scope = Depends(get_scope), r=Depends(get_redis)):
    m = repo_ops.metrics(s)
    return {**m, "certs_per_sec": (await read_state(r)).certs_per_sec}  # 0 when the heartbeat is stale


@router.get("/ops/log", response_model=Page[OpsLogItem])
def ops_log(since: datetime | None = None, channel: str | None = Query(None, enum=list(CHANNELS)),
            limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), s: Scope = Depends(get_scope)):
    rows = repo_ops.log_page(s, since=since, channel=channel, limit=limit, offset=offset)
    return {"items": [{k: v for k, v in x.items() if k != "total"} for x in rows],
            "total": rows[0]["total"] if rows else 0, "limit": limit, "offset": offset}
