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
    assert db.execute(sa.text("select confirm_reasons from domains where id=:d"), {"d": d}).scalar() is None


async def test_already_decided_domain_skipped(db, tmp_path):
    t = triage("paytm-kyc-verify.buzz")
    d, _ = repo.upsert_candidate(db, name="paytm-kyc-verify.buzz", etld1=t.etld1, cert_id=None, triage=t,
                                 source="certstream", ct_seen_at=datetime.now(timezone.utc))
    db.execute(sa.text("update domains set status='dismissed' where id=:d"), {"d": d})
    r = fr.FakeRedis(decode_responses=True)
    assert await enrich_worker.handle_one(d, conn=db, redis=r, evidence_dir=tmp_path, signing_key_hex="00" * 32) == "skipped"
