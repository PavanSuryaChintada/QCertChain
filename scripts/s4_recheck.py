"""S4: re-check a fixed set of live domains through the REAL enrichment worker (forced), so the reported verdicts come
from the shipped confirmation logic, not the logic that produced them first.

    PYTHONPATH=. python -m scripts.s4_recheck --ids reports/s4_domain_ids.json            enqueue (once)
    PYTHONPATH=. python -m scripts.s4_recheck --ids reports/s4_domain_ids.json --status   progress

The id set is the one the "before" diagnosis covered (scripts/diagnose_confirm.py --save-ids), so before and after
describe exactly the same domains. Each id is queued as a forced item for the pipeline operator's org; the worker
re-fetches the page (Playwright, SSRF-guarded, never interacting) and re-runs confirmation.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import redis.asyncio as aioredis
import sqlalchemy as sa

from services.api.workers.enrich_worker import QUEUE, item, pipeline_org_id
from services.config import SETTINGS

STARTED = "s4:recheck_started_at"


async def enqueue(ids: list[int]) -> None:
    r = aioredis.from_url(SETTINGS.redis_url, decode_responses=True)
    org = pipeline_org_id()
    await r.set(STARTED, datetime.now(timezone.utc).isoformat())
    for i in range(0, len(ids), 500):
        await r.rpush(QUEUE, *[item(d, org, force=True) for d in ids[i:i + 500]])
    print(f"queued {len(ids)} forced re-checks for org {org}; queue length now {await r.llen(QUEUE)}")
    await r.aclose()


async def status(ids: list[int]) -> None:
    r = aioredis.from_url(SETTINGS.redis_url, decode_responses=True)
    started, qlen = await r.get(STARTED), await r.llen(QUEUE)
    await r.aclose()
    with sa.create_engine(SETTINGS.database_url).connect() as c:
        done = c.execute(sa.text("""select count(*) from domain_verdicts where org_id = :o and domain_id = any(:ids)
                                    and verdict_at >= cast(:t as timestamptz)"""),
                         {"o": pipeline_org_id(), "ids": ids, "t": started}).scalar()
    print(json.dumps({"started": started, "rechecked": done, "of": len(ids), "queue_length": qlen}))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ids", required=True)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    ids = json.loads(Path(a.ids).read_text(encoding="utf-8"))
    asyncio.run(status(ids) if a.status else enqueue(ids))


if __name__ == "__main__":
    main()
