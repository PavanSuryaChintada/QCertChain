"""The public home page's live certificate panel (owner decision 2026-10-10). Keyless by design, like /orgs/public.
Certificate-log names only (nothing an organisation owns); a candidate's name is masked HERE, so its full name
never reaches a browser: a name match is suspicious, not verified (CLAUDE.md §2.2). No scores, ids or issuers. One
Redis read per CACHE_S, however many visitors."""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends

from services.api.deps import get_redis
from services.api.routes.stream import read_state
from services.api.workers.triage_worker import RECENT, RECENT_CANDIDATES, RECENT_CANDIDATES_N, RECENT_N

router = APIRouter()  # no key
CACHE_S = 2.0
HIDDEN = "•" * 6
_cache: tuple[float, dict] | None = None


def mask(name: str, etld1: str | None) -> str:
    """The registrable domain only (never a subdomain), with most of its first label hidden."""
    base = etld1 or ".".join(name.split(".")[-2:])
    label, _, suffix = base.partition(".")
    keep = 5 if len(label) > 7 else max(1, len(label) // 2)
    return label[:keep] + HIDDEN + (f".{suffix}" if suffix else "")


async def public_feed(r) -> dict:
    st = await read_state(r)
    plain = [json.loads(x) for x in await r.lrange(RECENT, 0, RECENT_N - 1)]
    cand = [json.loads(x) for x in await r.lrange(RECENT_CANDIDATES, 0, RECENT_CANDIDATES_N - 1)]
    return {"mode": st.mode, "connection": st.connection, "certs_per_sec": st.certs_per_sec,
            "recent": [{"name": d["name"], "ts": d["ts"]} for d in plain],
            "candidates": [{"name": mask(d["name"], d.get("etld1")), "ts": d["ts"]} for d in cand]}


@router.get("/certs/public")
async def certs_public(r=Depends(get_redis)) -> dict:
    global _cache
    now = time.monotonic()
    if _cache is None or now - _cache[0] >= CACHE_S:
        _cache = (now, await public_feed(r))
    return _cache[1]
