import json
from datetime import datetime, timezone

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
    stats = await process_batch(certs, redis=r, conn=db)
    assert stats == {"certs": 3, "names": 3, "candidates": 2, "new_candidates": 1}
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
    assert row.received_at is not None and row.received_at <= row.candidate_at
