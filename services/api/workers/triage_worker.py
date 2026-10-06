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

import redis.asyncio as aioredis
import sqlalchemy as sa

from services.api import repo
from services.api.db import engine
from services.config import SETTINGS
from services.ingest.certparse import CertRecord
from services.ingest.triage import triage, warm

STREAM, GROUP, ENRICH_QUEUE = "certs:raw", "triage", "enrich:queue"
LIVE_CHANNEL = "certs:live"
BATCH = 500
FEED_SOURCE = {"certstream": "live", "replay": "replay", "seed": "seed", "email": "email", "sample": "sample"}


async def process_batch(raw_certs: list[str], *, redis, conn: sa.Connection) -> dict:
    stats = {"certs": 0, "names": 0, "candidates": 0, "new_candidates": 0}
    feed: list[str] = []
    new_ids: list[int] = []
    for raw in raw_certs:
        rec = CertRecord.from_json(raw)
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
                    new_ids.append(domain_id)
            feed.append(json.dumps({"ts": rec.seen_at.isoformat(), "name": name, "etld1": t.etld1,
                                    "score": t.score, "is_candidate": t.is_candidate, "domain_id": domain_id,
                                    "issuer": rec.issuer, "source": FEED_SOURCE.get(rec.source, rec.source)},
                                   ensure_ascii=False))
    if stats["new_candidates"]:
        repo.log(conn, "triage", f"{stats['new_candidates']} new candidates from {stats['certs']} certificates",
                 context={"domain_ids": new_ids[:50]})
    async with redis.pipeline(transaction=False) as p:
        for f in feed:
            p.publish(LIVE_CHANNEL, f)
        for d in new_ids:
            p.lpush(ENRICH_QUEUE, d)
        await p.execute()
    return stats


async def main() -> None:
    warm()
    r = aioredis.from_url(SETTINGS.redis_url, decode_responses=True)
    try:
        await r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
    except aioredis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    while True:
        resp = await r.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=BATCH, block=5000)
        if not resp:
            continue
        ids, raws = [], []
        for _, entries in resp:
            for eid, fields in entries:
                ids.append(eid)
                raws.append(fields["cert"])
        with engine().begin() as conn:
            await process_batch(raws, redis=r, conn=conn)
        await r.xack(STREAM, GROUP, *ids)


if __name__ == "__main__":
    asyncio.run(main())
