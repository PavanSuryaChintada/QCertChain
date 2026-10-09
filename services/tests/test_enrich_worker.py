from datetime import datetime, timezone

import fakeredis.aioredis as fr
import nacl.signing
import pytest
import sqlalchemy as sa

from services.api import repo
from services.api.workers import enrich_worker
from services.enrich.confirm import ConfirmResult, Signal
from services.enrich.enrichers import Enrichment
from services.ingest.triage import triage

pytestmark = pytest.mark.db


async def test_handle_one_confirms_and_persists(db, tmp_path, monkeypatch):
    t = triage("sbi-verify-kyc.top")
    d, _ = repo.upsert_candidate(db, name="sbi-verify-kyc.top", etld1=t.etld1, cert_id=None, triage=t,
                                 source="certstream", ct_seen_at=datetime.now(timezone.utc))
    seen = {}

    async def fake_confirm(domain, brand, **kw):
        seen["domain"], seen["brand"] = domain, brand.name if brand else None
        return (ConfirmResult("confirmed", 0.9, [Signal("a", "strong", "x"), Signal("b", "strong", "y")], 2), None,
                Enrichment(ip_addresses=["203.0.113.9"], dom_hash="k1"))

    monkeypatch.setattr(enrich_worker, "confirm", fake_confirm)
    r = fr.FakeRedis(decode_responses=True)
    verdict = await enrich_worker.handle_one(d, conn=db, redis=r, evidence_dir=tmp_path,
                                             signing_key_hex=nacl.signing.SigningKey.generate().encode().hex())
    assert verdict == "confirmed" and seen == {"domain": "sbi-verify-kyc.top", "brand": "State Bank of India"}
    assert db.execute(sa.text("select count(*) from evidence_bundles")).scalar() == 1


async def test_rate_limited_is_requeued_not_persisted(db, tmp_path, monkeypatch):
    t = triage("hdfc-secure-update.click")
    d, _ = repo.upsert_candidate(db, name="hdfc-secure-update.click", etld1=t.etld1, cert_id=None, triage=t,
                                 source="certstream", ct_seen_at=datetime.now(timezone.utc))

    async def limited(domain, brand, **kw):
        return ConfirmResult("candidate", 0.0, [Signal("rate_limited", "weak", "x")], 0), None, Enrichment()

    monkeypatch.setattr(enrich_worker, "confirm", limited)
    r = fr.FakeRedis(decode_responses=True)
    verdict = await enrich_worker.handle_one(d, conn=db, redis=r, evidence_dir=tmp_path, signing_key_hex="00" * 32)
    assert verdict == "requeued" and await r.zcard(enrich_worker.RETRY_ZSET) == 1
    assert db.execute(sa.text("select confirm_reasons from org_domains where id=:d"), {"d": d}).scalar() is None


async def test_already_decided_domain_skipped(db, tmp_path):
    t = triage("paytm-kyc-verify.buzz")
    d, _ = repo.upsert_candidate(db, name="paytm-kyc-verify.buzz", etld1=t.etld1, cert_id=None, triage=t,
                                 source="certstream", ct_seen_at=datetime.now(timezone.utc))
    db.execute(sa.text("insert into domain_verdicts (domain_id, status) values (:d, 'dismissed')"), {"d": d})
    r = fr.FakeRedis(decode_responses=True)
    assert await enrich_worker.handle_one(d, conn=db, redis=r, evidence_dir=tmp_path, signing_key_hex="00" * 32) == "skipped"


async def test_row_not_yet_committed_is_requeued_not_dropped(db, tmp_path):
    """Producers push the id before their transaction commits: the worker may see no row yet."""
    r = fr.FakeRedis(decode_responses=True)
    v = await enrich_worker.handle_one(987654321, conn=db, redis=r, evidence_dir=tmp_path, signing_key_hex="00" * 32)
    assert v == "requeued" and await r.zcard(enrich_worker.RETRY_ZSET) == 1


async def test_missing_row_gives_up_after_a_few_attempts(db, tmp_path):
    r = fr.FakeRedis(decode_responses=True)
    for _ in range(enrich_worker.MISSING_ROW_ATTEMPTS):
        await enrich_worker.handle_one(55, conn=db, redis=r, evidence_dir=tmp_path, signing_key_hex="00" * 32)
    assert await enrich_worker.handle_one(55, conn=db, redis=r, evidence_dir=tmp_path,
                                          signing_key_hex="00" * 32) == "skipped"


async def test_unreachable_is_rechecked_later_with_backoff(db, tmp_path, monkeypatch):
    """TRD: unreachable stays a candidate. Kits often go live after the certificate is issued."""
    import time
    t = triage("kyc-sbi-verify.top")
    d, _ = repo.upsert_candidate(db, name="kyc-sbi-verify.top", etld1=t.etld1, cert_id=None, triage=t,
                                 source="certstream", ct_seen_at=datetime.now(timezone.utc))

    async def dead(domain, brand, **kw):
        return ConfirmResult("unreachable", 0.0, [Signal("not_assessable", "weak", "timeout")], 0), None, Enrichment()

    monkeypatch.setattr(enrich_worker, "confirm", dead)
    r = fr.FakeRedis(decode_responses=True)
    delays = []
    for _ in range(len(enrich_worker.RECHECK_DELAYS_S) + 1):
        before = time.time()
        assert await enrich_worker.handle_one(d, conn=db, redis=r, evidence_dir=tmp_path, signing_key_hex="00" * 32,
                                              force=True) == "unreachable"
        due = await r.zscore(enrich_worker.RETRY_ZSET, f"force:{d}")
        delays.append(None if due is None else round(due - before))
        await r.zrem(enrich_worker.RETRY_ZSET, f"force:{d}")
    assert delays[0] >= 300 and delays[1] > delays[0]
    assert delays[-1] is None  # gives up after the schedule (72 h)


async def test_kill_switch_reaches_confirmation_without_a_restart(db, tmp_path, monkeypatch):
    """S3c: setting the override in Redis changes the very next confirmation (no redeploy, no restart)."""
    from services.enrich import signal_switch
    t = triage("sbi-kyc-online.top")
    d, _ = repo.upsert_candidate(db, name="sbi-kyc-online.top", etld1=t.etld1, cert_id=None, triage=t,
                                 source="certstream", ct_seen_at=datetime.now(timezone.utc))
    seen = {}

    async def fake_confirm(domain, brand, **kw):
        seen.update(kw.get("signal_strengths") or {})
        return ConfirmResult("dismissed", 0.0, [], 0), None, Enrichment()

    monkeypatch.setattr(enrich_worker, "confirm", fake_confirm)
    r = fr.FakeRedis(decode_responses=True)
    await signal_switch.set_override(r, {"exfil": "off", "js_post": "off"})
    await enrich_worker.handle_one(d, conn=db, redis=r, evidence_dir=tmp_path,
                                   signing_key_hex=nacl.signing.SigningKey.generate().encode().hex())
    assert seen == {"exfil": "off", "js_post": "off"}


async def test_the_newest_candidate_is_checked_first():
    """Owner decision 2026-10-09: the checker is hours behind on one laptop, so oldest-first left every fresh row
    at the top of the queue unchecked ("Suspicious" only). Newest first gives the live view real verdicts."""
    r = fr.FakeRedis(decode_responses=True)
    for d in ("1", "2", "3"):  # triage pushes each new candidate onto the front
        await r.lpush(enrich_worker.QUEUE, d)
    assert [await enrich_worker.pop_next(r) for _ in range(3)] == ["3", "2", "1"]
    assert await enrich_worker.pop_next(r, timeout=1) is None


async def test_a_due_retry_goes_before_older_queued_items():
    r = fr.FakeRedis(decode_responses=True)
    await r.lpush(enrich_worker.QUEUE, "1", "2")
    await r.zadd(enrich_worker.RETRY_ZSET, {"9": 0})  # due long ago
    await enrich_worker._promote_retries(r)
    assert await enrich_worker.pop_next(r) == "9"
