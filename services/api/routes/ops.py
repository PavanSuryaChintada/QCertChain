"""Metrics, the ops log, and demo seeding."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from services.api import cursor
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
            limit: int = cursor.LimitQ, cursor_: str | None = Query(None, alias="cursor", max_length=512), s: Scope = Depends(get_scope)):
    rows = repo_ops.log_page(s, since=since, channel=channel, limit=limit, after=cursor.decode(cursor_, 1))
    return cursor.page(rows, limit, lambda r: [r["id"]])
