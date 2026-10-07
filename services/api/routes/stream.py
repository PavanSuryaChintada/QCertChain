"""Stream state and the live certificate feed (SSE, server-throttled to ~20 events/s). Shared platform data:
the public CT feed. Switching its mode is an admin action (routes/admin.py)."""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from services.api.deps import get_redis
from services.api.models import StreamState

router = APIRouter()
STATE, MODE_REQ, LIVE = "stream:state", "stream:mode_request", "certs:live"
STALE_AFTER_S = 15


async def triage_lag(r) -> int:
    """Certificates waiting for triage = entries after the triage group's last-delivered id plus delivered-but-
    unacked ones. NOT the stream length: acked entries stay in the stream until trimmed."""
    try:
        groups = await r.xinfo_groups("certs:raw")
    except Exception:
        return await r.xlen("certs:raw") if await r.exists("certs:raw") else 0
    g = next((x for x in groups if x.get("name") == "triage"), None)
    if g is None:
        return await r.xlen("certs:raw")
    if g.get("lag") is not None:
        return int(g["lag"]) + int(g.get("pending", 0))
    after = await r.xrange("certs:raw", min=f"({g['last-delivered-id']}", max="+")
    return len(after) + int(g.get("pending", 0))


async def read_state(r) -> StreamState:
    st = await r.hgetall(STATE)
    req = await r.hgetall(MODE_REQ)
    depth = {"certs_raw": await triage_lag(r), "enrich": await r.llen("enrich:queue")}
    hb = datetime.fromisoformat(st["last_heartbeat"]) if st.get("last_heartbeat") else None
    # Ingest heartbeats every 5 s. Three missed beats = the process is gone: never show a dead stream as live.
    stale = hb is None or (datetime.now(timezone.utc) - hb).total_seconds() > STALE_AFTER_S
    return StreamState(
        mode=req.get("mode") or st.get("mode") or "live",
        connection="down" if stale else (st.get("connection") or "down"),
        certs_per_sec=0 if stale else float(st.get("certs_per_sec") or 0),
        names_per_sec=0 if stale else float(st.get("names_per_sec") or 0),
        candidates_per_min=float(st.get("candidates_per_min") or 0), queue_depth=depth,
        replay_file=st.get("replay_file") or None,
        last_heartbeat=hb)


@router.get("/stream/state", response_model=StreamState)
async def stream_state(r=Depends(get_redis)):
    return await read_state(r)


async def live_events(r, max_per_sec: int = 20, heartbeat_s: float = 5.0) -> AsyncIterator[str]:
    """Token bucket: at most max_per_sec cert events per second, excess dropped (the browser and the
    analyst cannot read 3,000/s). Candidates are never dropped while the bucket is empty: they wait."""
    pubsub = r.pubsub()
    await pubsub.subscribe(LIVE)
    tokens, last_fill, last_hb = float(max_per_sec), time.monotonic(), 0.0
    try:
        while True:
            now = time.monotonic()
            tokens = min(float(max_per_sec), tokens + (now - last_fill) * max_per_sec)
            last_fill = now
            if now - last_hb >= heartbeat_s:
                st = await r.hgetall(STATE)
                yield "event: heartbeat\ndata: " + json.dumps(
                    {"ts": datetime.now(timezone.utc).isoformat(),
                     "certs_per_sec": float(st.get("certs_per_sec") or 0)}) + "\n\n"
                last_hb = now
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.25)
            if msg is None:
                continue
            data = msg["data"]
            if tokens < 1:
                if not json.loads(data).get("is_candidate"):
                    continue
                await asyncio.sleep((1 - tokens) / max_per_sec)
                tokens = 1.0
            tokens -= 1
            yield f"event: cert\ndata: {data}\n\n"
    finally:
        await pubsub.unsubscribe(LIVE)
        await pubsub.aclose()


@router.get("/certs/live")
async def certs_live(r=Depends(get_redis)):
    return StreamingResponse(live_events(r), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
