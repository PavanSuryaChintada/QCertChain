"""Enrich worker: enrich:queue -> confirm (fetch + enrich, observe only) -> persist verdict, graph, campaign,
evidence bundle, unsent report, anchor-queue entry. Run N replicas (docker-compose: 4).

A forced re-confirm (POST /domains/{id}/confirm) pushes onto the same queue with a 'force:' prefix.
A per-host rate-limited fetch is re-queued with a delay, never recorded as a verdict.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import redis.asyncio as aioredis
import sqlalchemy as sa

from services.api import repo
from services.api.db import engine
from services.api.pipeline import persist_result
from services.config import SETTINGS
from functools import lru_cache

from services.enrich.confirm import confirm
from services.ml.brand_refs import load_brand_favicons

from services.ingest.triage import _brands, warm

QUEUE, RETRY_ZSET = "enrich:queue", "enrich:retry"
MISSING_ATTEMPTS_KEY = "enrich:missing_attempts"
MISSING_ROW_ATTEMPTS = 5  # producers may push the id before their transaction commits
MISSING_ROW_DELAY_S = 3
# TRD: an unreachable domain stays a candidate. Phishing kits are often deployed after the certificate is
# issued, so re-check over 72 h instead of judging once, seconds after issuance.
RECHECK_DELAYS_S = (300, 1800, 7200, 21600, 86400, 259200)
RECHECK_KEY = "enrich:recheck_attempts"


@lru_cache(maxsize=1)
def _favicons() -> dict[str, set[str]]:
    return load_brand_favicons()  # real brand favicons -> the strong favicon_brand_match signal
RETRY_DELAY_S = 30


def _limiter(r):
    async def acquire(host: str) -> bool:
        return bool(await r.set(f"ratelimit:{host}", "1", nx=True, ex=max(1, int(SETTINGS.per_host_rate_limit_s))))
    return acquire


async def handle_one(domain_id: int, *, conn: sa.Connection, redis, evidence_dir: Path | str,
                     signing_key_hex: str, force: bool = False) -> str:
    row = conn.execute(sa.text("select name, status, brand_matched, source, cert_id from domains where id = :d"),
                       {"d": domain_id}).one_or_none()
    if row is None:
        n = await redis.hincrby(MISSING_ATTEMPTS_KEY, str(domain_id), 1)
        if n > MISSING_ROW_ATTEMPTS:
            await redis.hdel(MISSING_ATTEMPTS_KEY, str(domain_id))
            return "skipped"
        await redis.zadd(RETRY_ZSET, {str(domain_id): time.time() + MISSING_ROW_DELAY_S})
        return "requeued"
    await redis.hdel(MISSING_ATTEMPTS_KEY, str(domain_id))
    if row.status != "candidate" and not force:
        return "skipped"
    issuer = conn.execute(sa.text("select issuer from certificates where id = :c"), {"c": row.cert_id}).scalar() \
        if row.cert_id else None
    brand = next((b for b in _brands().brands if b.name == row.brand_matched), None)  # cached index
    t0 = time.perf_counter()
    result, page, e = await confirm(row.name, brand, known_kits=repo.known_kits(conn), brand_favicons=_favicons(),
                                    issuer=issuer, limiter=_limiter(redis))
    if result.signals and result.signals[0].name == "rate_limited":
        await redis.zadd(RETRY_ZSET, {str(domain_id): time.time() + RETRY_DELAY_S})
        return "requeued"
    persist_result(conn, domain_id, row.name, result, page, e, evidence_dir=evidence_dir,
                   signing_key_hex=signing_key_hex, source=row.source)
    if result.verdict == "unreachable":
        n = await redis.hincrby(RECHECK_KEY, str(domain_id), 1)
        if n <= len(RECHECK_DELAYS_S):
            await redis.zadd(RETRY_ZSET, {f"force:{domain_id}": time.time() + RECHECK_DELAYS_S[n - 1]})
        else:
            await redis.hdel(RECHECK_KEY, str(domain_id))
    else:
        await redis.hdel(RECHECK_KEY, str(domain_id))
    repo.log(conn, "enrich", f"{row.name}: {result.verdict} in {time.perf_counter() - t0:.1f}s",
             context={"domain_id": domain_id, "via": page.via if page else None})
    return result.verdict


async def _promote_retries(r) -> None:
    due = await r.zrangebyscore(RETRY_ZSET, 0, time.time())
    if due:
        await r.zrem(RETRY_ZSET, *due)
        await r.rpush(QUEUE, *due)


async def worker(r, sem: asyncio.Semaphore) -> None:
    while True:
        await _promote_retries(r)
        item = await r.brpop(QUEUE, timeout=5)
        if not item:
            continue
        raw = item[1]
        force = raw.startswith("force:")
        domain_id = int(raw.removeprefix("force:"))
        async with sem:
            try:
                with engine().begin() as conn:
                    await handle_one(domain_id, conn=conn, redis=r, evidence_dir=SETTINGS.evidence_dir,
                                     signing_key_hex=SETTINGS.collector_private_key, force=force)
            except Exception as exc:  # one bad domain never stops the worker; the error is logged
                with engine().begin() as conn:
                    repo.log(conn, "enrich", f"domain {domain_id}: {type(exc).__name__}: {exc}"[:500], severity=3)


async def main() -> None:
    warm()
    if not SETTINGS.collector_private_key:
        raise SystemExit("COLLECTOR_PRIVATE_KEY is not set (python -m scripts.genkey)")
    r = aioredis.from_url(SETTINGS.redis_url, decode_responses=True)
    sem = asyncio.Semaphore(SETTINGS.enrich_workers)
    await asyncio.gather(*(worker(r, sem) for _ in range(SETTINGS.enrich_workers)))


if __name__ == "__main__":
    asyncio.run(main())
