"""Metrics, the ops log, and demo seeding."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from services.api import cursor
from services.api.deps import Scope, get_ledger, get_redis, get_scope
from services.api.models import Metrics, OpsLogItem, Page
from services.api.repos import ops as repo_ops
from services.api.routes.stream import read_state

router = APIRouter()
CHANNELS = ("stream", "triage", "confirm", "enrich", "graph", "interdict", "evidence", "ledger", "email", "system")


@router.get("/metrics", response_model=Metrics)
async def metrics(s: Scope = Depends(get_scope), r=Depends(get_redis)):
    m = repo_ops.metrics(s)
    return {**m, "certs_per_sec": (await read_state(r)).certs_per_sec}  # 0 when the heartbeat is stale


def _components(stream, counts: dict, ledger_up: bool) -> dict:
    """Per-stage status for the architecture diagram: ok / degraded / failed (failed renders grey, never red)."""
    conn = stream.connection
    ct = ("ok", f"{stream.certs_per_sec:.0f} certs/s, {conn}") if conn in ("connected", "replay") else \
        ("degraded", "reconnecting to the CT stream") if conn == "reconnecting" else ("failed", "no CT stream heartbeat")
    lag = stream.queue_depth.get("certs_raw", 0)
    triage = ("ok" if lag < 10_000 else "degraded" if lag < 100_000 else "failed", f"{lag:,} certificates waiting")
    enq = stream.queue_depth.get("enrich", 0)
    enrich = ("ok" if enq < 500 else "degraded" if enq < 5_000 else "failed", f"{enq:,} candidates waiting for a fetch")
    graph = ("ok" if counts["campaigns_without_graph"] == 0 else "degraded",
             f"{counts['campaigns_active']} campaigns" + (f", {counts['campaigns_without_graph']} without a snapshot"
                                                          if counts["campaigns_without_graph"] else ""))
    depth = counts["anchor_queue_depth"]
    ledger = ("failed", f"chain unreachable, {depth} writes queued") if not ledger_up else \
        ("ok" if depth < 100 else "degraded", f"{depth} writes queued")
    return {"ct": {"status": ct[0], "detail": ct[1]}, "triage": {"status": triage[0], "detail": triage[1]},
            "confirm": {"status": enrich[0], "detail": f"{counts['confirmations_last_hour']} confirmations in the last hour"},
            "enrich": {"status": enrich[0], "detail": enrich[1]},
            "graph": {"status": graph[0], "detail": graph[1]},
            "interdiction": {"status": "ok", "detail": f"{counts['plans_today']} plans today"},
            "evidence": {"status": "ok", "detail": f"{counts['bundles_total']} bundles"},
            "ledger": {"status": ledger[0], "detail": ledger[1]},
            "email": {"status": "ok", "detail": f"{counts['email_analyses']} analyses"}}


@router.get("/status")
async def status(s: Scope = Depends(get_scope), r=Depends(get_redis), ledger=Depends(get_ledger)):
    """ONE batched poll for the console chrome (top bar, rail, architecture page): org, key kind, stream, counters,
    per-component status, and /health. Keeps the published demo key far under its 60 requests/minute."""
    from services.api.health import report
    counts = repo_ops.status_counts(s)
    stream = await read_state(r)
    try:
        ledger_up = bool(ledger.available())
    except Exception:
        ledger_up = False
    metrics = {k: counts[k] for k in ("campaigns_active", "domains_confirmed", "domains_candidate", "plans_today",
                                      "bundles_today", "anchor_queue_depth", "candidates_last_hour",
                                      "confirmations_last_hour")}
    return {"org": {"slug": s.org_slug, "name": counts["org_name"]}, "key_kind": s.kind,
            "stream": stream.model_dump(mode="json"), "metrics": {**metrics, "certs_per_sec": stream.certs_per_sec},
            "ledger": {"available": ledger_up, "queue_depth": counts["anchor_queue_depth"]},
            "components": _components(stream, counts, ledger_up), "health": report()}


@router.get("/scaling")
def scaling():
    """The scaling benchmark (scripts/scaling_benchmark.py): synthetic campaigns n = 10..80, k = n/4. Platform data,
    readable with any key; nothing in it is organisation data. Extrapolated values are flagged per point."""
    import json

    from services.config import ROOT
    p = ROOT / "reports/scaling.json"
    if not p.exists():
        return {"unavailable": "reports/scaling.json not generated yet (python -m scripts.scaling_benchmark)"}
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/metrics/report")
def metrics_report(s: Scope = Depends(get_scope)):
    """The measured evaluation (reports/metrics.json, produced by scripts/evaluate.py). Platform-level numbers,
    identical for every organisation; nothing in it is organisation data. A section that was not measured is
    {"unavailable": reason}, never a placeholder."""
    import json

    from services.config import ROOT
    p = ROOT / "reports/metrics.json"
    if not p.exists():
        return {"unavailable": "reports/metrics.json not generated yet (python -m scripts.evaluate)"}
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/ops/log", response_model=Page[OpsLogItem])
def ops_log(since: datetime | None = None, channel: str | None = Query(None, enum=list(CHANNELS)),
            limit: int = cursor.LimitQ, cursor_: str | None = Query(None, alias="cursor", max_length=512), s: Scope = Depends(get_scope)):
    rows = repo_ops.log_page(s, since=since, channel=channel, limit=limit, after=cursor.decode(cursor_, 1))
    return cursor.page(rows, limit, lambda r: [r["id"]])
