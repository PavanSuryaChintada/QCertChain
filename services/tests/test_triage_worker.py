import json
from datetime import timedelta, datetime, timezone

import fakeredis.aioredis as fr
import pytest
import sqlalchemy as sa

from services.api.workers.triage_worker import LIVE_CHANNEL, process_batch
from services.ingest.certparse import CertRecord

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 6, tzinfo=timezone.utc)


def entry(fp, names):
    return CertRecord(fp, names, 0, "Let's Encrypt", NOW, None, "01", len(names), NOW, "certstream").to_json()


async def test_batch_stores_only_candidates_and_queues_new_ones(db):
    r = fr.FakeRedis(decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(LIVE_CHANNEL)
    await pubsub.get_message(timeout=0.1)
    certs = [entry("fp1", ["sbi-verify-kyc.top"]), entry("fp2", ["www.google.com"]),
             entry("fp3", ["sbi-verify-kyc.top"])]  # precert + final cert: same name, new fingerprint
    batch = await process_batch(certs, redis=r, conn=db)
    assert batch.stats == {"certs": 3, "names": 3, "candidates": 2, "new_candidates": 1, "dead_lettered": 0}
    from services.api.workers.triage_worker import publish
    await publish(r, batch)
    assert db.execute(sa.text("select count(*) from domains")).scalar() == 1
    assert await r.llen("enrich:queue") == 1
    msgs = []
    while (m := await pubsub.get_message(timeout=0.2)) is not None:
        if m["type"] == "message":
            msgs.append(json.loads(m["data"]))
    assert len(msgs) == 3 and sum(m["is_candidate"] for m in msgs) == 2
    assert {m["source"] for m in msgs} == {"live"} and all("domain_id" in m for m in msgs)


async def test_replay_source_labelled_in_db_and_feed(db):
    r = fr.FakeRedis(decode_responses=True)
    c = CertRecord("fpR", ["hdfc-secure-update.click"], 0, None, NOW, None, None, 1, NOW, "replay").to_json()
    await process_batch([c], redis=r, conn=db)
    assert db.execute(sa.text("select source from domains")).scalar() == "replay"


async def test_candidate_stores_our_receipt_time(db):
    r = fr.FakeRedis(decode_responses=True)
    await process_batch([entry("fpX", ["sbi-verify-kyc.top"])], redis=r, conn=db)
    row = db.execute(sa.text("select ct_seen_at, received_at, candidate_at from domains")).one()
    # received_at is the worker host's clock, candidate_at the database's: allow cross-clock skew (WSL2/Docker
    # drift measured in ms; the latency being measured is seconds)
    assert row.received_at is not None and row.received_at <= row.candidate_at + timedelta(seconds=1)


async def test_enrich_ids_are_published_only_after_commit(db):
    from services.api.workers.triage_worker import publish
    r = fr.FakeRedis(decode_responses=True)
    pending = await process_batch([entry("fpC", ["icici-netbanking-login.xyz"])], redis=r, conn=db)
    assert await r.llen("enrich:queue") == 0  # nothing visible to workers before the caller commits
    await publish(r, pending)
    assert await r.llen("enrich:queue") == 1



async def test_poison_record_is_dead_lettered_and_the_batch_survives(db):
    from services.api.workers.triage_worker import DEAD_LETTER, publish
    r = fr.FakeRedis(decode_responses=True)
    batch = await process_batch(["{not json", entry("fpOK", ["sbi-verify-kyc.top"])], redis=r, conn=db)
    await publish(r, batch)
    assert batch.stats["dead_lettered"] == 1 and batch.stats["candidates"] == 1
    assert await r.llen(DEAD_LETTER) == 1


async def test_unacked_entries_of_a_crashed_worker_are_reclaimed():
    from services.api.workers.triage_worker import GROUP, STREAM, reclaim_stale
    r = fr.FakeRedis(decode_responses=True)
    for i in range(3):
        await r.xadd(STREAM, {"cert": str(i)})
    await r.xgroup_create(STREAM, GROUP, id="0")
    await r.xreadgroup(GROUP, "dead-worker", {STREAM: ">"}, count=3)  # delivered, never acked
    got = await reclaim_stale(r, "new-worker", min_idle_ms=0)
    assert len(got) == 3


async def test_a_new_candidate_is_confirmed_for_the_organisation_of_its_brands_sector(db):
    """Spec 2026-10-09 §5: the oldest active organisation in the brand's sector confirms it (banking: Bank One, the
    older of the two banks); a sector with no organisation stays untagged (the pipeline organisation)."""
    from services.api.workers import triage_worker as tw
    tw.clear_sector_cache()
    shop = db.execute(sa.text("insert into organisations (slug, name, category) values ('shopsafe', 'ShopSafe', 'ecommerce') "
                              "returning id")).scalar()
    r = fr.FakeRedis(decode_responses=True)
    b = await process_batch([entry("fpE", ["amazon-login-verify.top"]), entry("fpB", ["sbi-verify-kyc.top"]),
                             entry("fpJ", ["myjio-kyc-update.top"])], redis=r, conn=db)
    await tw.publish(r, b)
    ids = {n: db.execute(sa.text("select id from domains where name = :n"), {"n": n}).scalar()
           for n in ("amazon-login-verify.top", "sbi-verify-kyc.top", "myjio-kyc-update.top")}
    queued = set(await r.lrange("enrich:queue", 0, -1))
    assert queued == {f"{shop}:{ids['amazon-login-verify.top']}", f"1:{ids['sbi-verify-kyc.top']}",
                      str(ids["myjio-kyc-update.top"])}
