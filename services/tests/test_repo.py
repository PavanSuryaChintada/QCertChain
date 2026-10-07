import json
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

from services.api import repo
from services.enrich.confirm import ConfirmResult, Signal
from services.enrich.enrichers import Enrichment
from services.ingest.certparse import CertRecord
from services.ingest.triage import triage

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 6, 3, 2, 11, tzinfo=timezone.utc)


def rec(fp="fp1", names=("sbi-verify-kyc.top",)):
    return CertRecord(fp, list(names), 0, "Let's Encrypt", NOW, None, "01", len(names), NOW, "certstream")


def test_upsert_cert_idempotent_on_fingerprint(db):
    assert repo.upsert_cert(db, rec()) == repo.upsert_cert(db, rec())


def test_upsert_candidate_once_and_keeps_first_timestamps(db):
    cid = repo.upsert_cert(db, rec())
    t = triage("sbi-verify-kyc.top")
    a, created_a = repo.upsert_candidate(db, name="sbi-verify-kyc.top", etld1=t.etld1, cert_id=cid, triage=t,
                                         source="certstream", ct_seen_at=NOW)
    first = db.execute(sa.text("select candidate_at, ct_seen_at from domains where id=:i"), {"i": a}).one()
    b, created_b = repo.upsert_candidate(db, name="sbi-verify-kyc.top", etld1=t.etld1, cert_id=cid, triage=t,
                                         source="certstream", ct_seen_at=datetime(2027, 1, 1, tzinfo=timezone.utc))
    assert a == b and created_a and not created_b
    assert db.execute(sa.text("select candidate_at, ct_seen_at from domains where id=:i"), {"i": a}).one() == first
    row = db.execute(sa.text("select status, triage_score, brand_matched, triage_reasons from org_domains where id=:i"),
                     {"i": a}).one()
    assert row.status == "candidate" and row.brand_matched == "State Bank of India"
    assert {r["feature"] for r in row.triage_reasons["reasons"]} >= {"brand_token_exact"}


def test_set_confirmation_stores_reasons(db):
    t = triage("sbi-verify-kyc.top")
    d, _ = repo.upsert_candidate(db, name="sbi-verify-kyc.top", etld1=t.etld1, cert_id=None, triage=t,
                                 source="certstream", ct_seen_at=NOW)
    res = ConfirmResult("confirmed", 0.91, [Signal("credential_post_foreign_origin", "strong", "x"),
                                             Signal("kit_dom_hash_match", "strong", "y")], 2)
    repo.set_confirmation(db, d, res)
    row = db.execute(sa.text("select status, confirmed_at, confidence, confirm_reasons from org_domains where id=:i"),
                     {"i": d}).one()
    assert row.status == "confirmed" and row.confirmed_at and row.confirm_reasons["strong_count"] == 2


def test_confirmed_without_signals_rejected_by_db(db):
    t = triage("sbi-verify-kyc.top")
    d, _ = repo.upsert_candidate(db, name="sbi-verify-kyc.top", etld1=t.etld1, cert_id=None, triage=t,
                                 source="certstream", ct_seen_at=NOW)
    with pytest.raises(sa.exc.IntegrityError):
        repo.set_confirmation(db, d, ConfirmResult("confirmed", 0.9, [], 2))


def test_enrichment_nodes_edges(db):
    t = triage("sbi-verify-kyc.top")
    d, _ = repo.upsert_candidate(db, name="sbi-verify-kyc.top", etld1=t.etld1, cert_id=None, triage=t,
                                 source="certstream", ct_seen_at=NOW)
    repo.save_enrichment(db, d, Enrichment(ip_addresses=["203.0.113.9"], nameservers=["ns1.x.top"], partial=True,
                                           errors={"rdap": "timeout"}))
    n1 = repo.upsert_node(db, "ip", "203.0.113.9")
    assert repo.upsert_node(db, "ip", "203.0.113.9") == n1
    repo.add_edge(db, d, n1, 0.8)
    repo.add_edge(db, d, n1, 0.8)  # idempotent
    assert db.execute(sa.text("select count(*) from graph_edges")).scalar() == 1
    assert db.execute(sa.text("select domain_count from infra_nodes where id=:i"), {"i": n1}).scalar() == 1
    assert db.execute(sa.text("select partial from enrichment where domain_id=:i"), {"i": d}).scalar() is True


def test_known_kits_and_ops_log_and_anchor_queue(db):
    repo.add_known_kit(db, "abc", "kit-a", "seed")
    repo.add_known_kit(db, "abc", "kit-a", "seed")
    assert repo.known_kits(db) == {"abc": "kit-a"}
    repo.log(db, "triage", "hello", context={"x": 1})
    assert db.execute(sa.text("select message from ops_log")).scalar() == "hello"
    qid = repo.enqueue_anchor(db, "evidence", {"bundle_id": "b"})
    assert db.execute(sa.text("select payload from anchor_queue where id=:i"), {"i": qid}).scalar() == {"bundle_id": "b"}


def test_every_verdict_is_timestamped_for_response_time_analysis(db):
    for verdict, name in (("dismissed", "a-sbi-kyc.top"), ("unreachable", "b-sbi-kyc.top")):
        t = triage(name)
        d, _ = repo.upsert_candidate(db, name=name, etld1=t.etld1, cert_id=None, triage=t, source="certstream",
                                     ct_seen_at=NOW)
        repo.set_confirmation(db, d, ConfirmResult(verdict, 0.0, [Signal("x", "weak", "y")], 0))
        assert db.execute(sa.text("select verdict_at from org_domains where id=:d"), {"d": d}).scalar() is not None
