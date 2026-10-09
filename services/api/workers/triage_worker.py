"""Triage worker: certs:raw (Redis Stream) -> triage every name -> candidates to Postgres -> enrich:queue.

Non-candidates never reach Postgres (TRD §6 retention). Every result goes to the live feed channel;
the API throttles that feed to <= 20 events/s for the console. Scale by running more replicas: they
share the consumer group.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import time
from collections import deque
from dataclasses import dataclass, field

import redis.asyncio as aioredis
import sqlalchemy as sa

from services.api import repo
from services.api.db import engine
from services.config import SETTINGS
from services.ingest.certparse import CertRecord
from services.ingest.triage import triage, warm

STREAM, GROUP, ENRICH_QUEUE = "certs:raw", "triage", "enrich:queue"
LIVE_CHANNEL = "certs:live"
DEAD_LETTER = "certs:dead"
BATCH = 500
FEED_SOURCE = {"certstream": "live", "replay": "replay", "seed": "seed", "email": "email", "sample": "sample"}
# The public home page's live panel (routes/public.py): the newest names, and the newest candidates kept apart
# because they are rare. Certificate logs only: the email analyzer's and seeded names belong to organisations.
RECENT, RECENT_CANDIDATES = "certs:recent", "certs:recent_candidates"
RECENT_N, RECENT_CANDIDATES_N = 6, 3
PUBLIC_SOURCES = {"live", "replay"}


SECTOR_TTL_S = 60.0
_sector_cache: tuple[float, dict[str, int]] | None = None


def clear_sector_cache() -> None:
    global _sector_cache
    _sector_cache = None


def sector_orgs(conn: sa.Connection) -> dict[str, int]:
    """Category -> the oldest active organisation in it (ties by id). Cached for a minute: a new organisation starts
    receiving its sector's candidates within that time."""
    global _sector_cache
    now = time.monotonic()
    if _sector_cache and now - _sector_cache[0] < SECTOR_TTL_S:
        return _sector_cache[1]
    out: dict[str, int] = {}
    for category, oid in repo.sector_orgs(conn):
        out.setdefault(category, oid)
    _sector_cache = (now, out)
    return out


def queue_item(conn: sa.Connection, domain_id: int, brand: str | None) -> str:
    """Spec 2026-10-09 §5: confirmed on behalf of the organisation that owns the brand's sector. No brand, or no
    organisation in that sector: untagged, so the pipeline organisation confirms it (as before)."""
    from services.api.platform import brand_sectors
    sector = brand_sectors().get(brand) if brand else None
    oid = sector_orgs(conn).get(sector) if sector else None
    return f"{oid}:{domain_id}" if oid else str(domain_id)


@dataclass
class Batch:
    stats: dict
    feed: list[str] = field(default_factory=list)
    new_ids: list[int] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)  # enrich queue items: "<org_id>:<domain_id>" or "<domain_id>"
    dead: list[str] = field(default_factory=list)
    recent: deque = field(default_factory=lambda: deque(maxlen=RECENT_N))
    recent_candidates: deque = field(default_factory=lambda: deque(maxlen=RECENT_CANDIDATES_N))

    def add_feed(self, item: dict) -> None:
        f = json.dumps(item, ensure_ascii=False)
        self.feed.append(f)
        if item["source"] in PUBLIC_SOURCES:
            (self.recent_candidates if item["is_candidate"] else self.recent).append(f)


async def process_batch(raw_certs: list[str], *, redis, conn: sa.Connection) -> Batch:
    """Database writes only. Redis effects are returned and published by `publish` AFTER the caller commits:
    pushing an id before the commit let an enrich worker look for a row that did not exist yet."""
    b = Batch({"certs": 0, "names": 0, "candidates": 0, "new_candidates": 0, "dead_lettered": 0})
    stats = b.stats
    for raw in raw_certs:
        try:
            rec = CertRecord.from_json(raw)
        except Exception:  # a poison record is kept for inspection, never allowed to kill the batch
            b.dead.append(raw if isinstance(raw, str) else repr(raw))
            stats["dead_lettered"] += 1
            continue
        stats["certs"] += 1
        cert_id = None
        for name in rec.names:
            stats["names"] += 1
            t = triage(name, issuer=rec.issuer, san_count=rec.san_count)
            domain_id = None
            if t.is_candidate:
                stats["candidates"] += 1
                if cert_id is None:
                    cert_id = repo.upsert_cert(conn, rec)
                domain_id, created = repo.upsert_candidate(conn, name=name, etld1=t.etld1, cert_id=cert_id, triage=t,
                                                          source=rec.source, ct_seen_at=rec.seen_at,
                                                          received_at=rec.received_at)
                if created:
                    stats["new_candidates"] += 1
                    b.new_ids.append(domain_id)
                    b.queue.append(queue_item(conn, domain_id, t.brand))
            b.add_feed({"ts": rec.seen_at.isoformat(), "name": name, "etld1": t.etld1, "score": t.score,
                        "is_candidate": t.is_candidate, "domain_id": domain_id, "issuer": rec.issuer,
                        "source": FEED_SOURCE.get(rec.source, rec.source)})
    if stats["new_candidates"]:
        repo.log(conn, "triage", f"{stats['new_candidates']} new candidates from {stats['certs']} certificates",
                 context={"domain_ids": b.new_ids[:50]})
    return b


async def publish(redis, b: Batch) -> None:
    async with redis.pipeline(transaction=False) as p:
        for f in b.feed:
            p.publish(LIVE_CHANNEL, f)
        for d in b.queue:
            p.lpush(ENRICH_QUEUE, d)
        for raw in b.dead:
            p.lpush(DEAD_LETTER, raw[:10_000])
        for key, items, n in ((RECENT, b.recent, RECENT_N), (RECENT_CANDIDATES, b.recent_candidates, RECENT_CANDIDATES_N)):
            if items:
                p.lpush(key, *items)  # the batch's last item ends up first: newest first
                p.ltrim(key, 0, n - 1)
        await p.execute()


async def reclaim_stale(r, consumer: str, min_idle_ms: int = 60_000) -> list[tuple[str, dict]]:
    """Entries delivered to a worker that died before XACK stay pending forever unless claimed."""
    claimed: dict[str, dict] = {}
    start = "0-0"
    for _ in range(10_000):  # bounded: never spin forever
        res = await r.xautoclaim(STREAM, GROUP, consumer, min_idle_time=min_idle_ms, start_id=start, count=500)
        nxt, entries = res[0], res[1]
        fresh = [(eid, f) for eid, f in entries if f and eid not in claimed]
        claimed.update(fresh)
        # Redis signals completion with cursor 0-0; also stop if the cursor repeats or nothing new arrives
        if not fresh or nxt in ("0-0", b"0-0") or nxt == start:
            break
        start = nxt
    return list(claimed.items())


async def _handle(r, conn_factory, ids: list[str], raws: list[str]) -> None:
    with conn_factory() as conn:
        b = await process_batch(raws, redis=r, conn=conn)
    await publish(r, b)  # after commit
    await r.xack(STREAM, GROUP, *ids)


async def main() -> None:
    warm()
    r = aioredis.from_url(SETTINGS.redis_url, decode_responses=True)
    try:
        await r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
    except aioredis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    stale = await reclaim_stale(r, consumer)
    if stale:
        await _handle(r, engine().begin, [e for e, _ in stale], [f.get("cert", "") for _, f in stale])
    while True:
        resp = await r.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=BATCH, block=5000)
        if not resp:
            continue
        ids, raws = [], []
        for _, entries in resp:
            for eid, fields in entries:
                ids.append(eid)
                raws.append(fields.get("cert", ""))
        try:
            await _handle(r, engine().begin, ids, raws)
        except Exception as e:  # database blip: leave the batch un-acked; it is reclaimed and retried
            print(f"triage worker: batch failed, will be retried: {type(e).__name__}: {e}", flush=True)
            await asyncio.sleep(2)
            for eid, f in await reclaim_stale(r, consumer, min_idle_ms=0):
                pass  # claimed back to this consumer; the next loop re-reads pending below
            pending = await r.xreadgroup(GROUP, consumer, {STREAM: "0"}, count=BATCH)
            for _, entries in pending or []:
                if entries:
                    try:
                        await _handle(r, engine().begin, [e for e, _ in entries], [f.get("cert", "") for _, f in entries])
                    except Exception as e2:
                        print(f"triage worker: retry failed: {type(e2).__name__}: {e2}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
