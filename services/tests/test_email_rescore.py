"""Owner decision 2 (option B): an email is RE-SCORED when one of its link (or sender) domains is confirmed later.

That is the cross-signal correlation the brief asks for, and it fixes the cold start without touching the rule:
malicious still needs two strong signals, and the database still enforces it.
"""
from pathlib import Path

import pytest
import sqlalchemy as sa

from services.api import repo
from services.api.db import set_org_context
from services.api.pipeline import persist_result
from services.email.analyze import analyze, db_lookup, persist_and_correlate
from services.enrich.enrichers import Enrichment
from services.ingest.brands import load_brands
from services.config import SETTINGS
from services.tests.test_pipeline import KEY, confirmed, page

pytestmark = pytest.mark.db
SPOOF = Path("services/email/samples/p01_display_spoof_dmarc_fail.eml").read_bytes()
LINK = "sbi-kyc-verify-17.example"
BR = load_brands(SETTINGS.brands_file)


def _cold_email(db):
    v = analyze(SPOOF, brands=BR, lookup=db_lookup(db))
    aid, new_ids = persist_and_correlate(db, v, "analyst")
    assert v.verdict == "suspicious" and v.strong_count == 1  # cold start: one strong signal only
    link_id = db.execute(sa.text("select id from org_domains where name = :n"), {"n": LINK}).scalar_one()
    return aid, link_id


def test_confirming_the_link_domain_rescores_the_email_to_malicious(db, tmp_path):
    aid, link_id = _cold_email(db)
    persist_result(db, link_id, LINK, confirmed(), page(LINK), Enrichment(ip_addresses=["203.0.113.9"]),
                   evidence_dir=tmp_path, signing_key_hex=KEY)
    row = db.execute(sa.text("select verdict, strong_count, signals, linked_domain_ids, verdict_history, rescored_at "
                             "from email_analyses where id = :i"), {"i": aid}).mappings().one()
    assert row["verdict"] == "malicious" and row["strong_count"] == 2
    assert any(s["name"] == "link_domain_confirmed" and "re-scored" in s["detail"] for s in row["signals"])
    assert link_id in row["linked_domain_ids"] and row["rescored_at"] is not None
    h = row["verdict_history"]
    assert h[-1]["from"] == "suspicious" and h[-1]["to"] == "malicious" and LINK in h[-1]["reason"]


def test_rescoring_never_crosses_organisations(db, tmp_path):
    aid, link_id = _cold_email(db)                       # org1 analysed the email
    set_org_context(db, 2)                               # org2 confirms the same (shared) name independently
    pub = db.execute(sa.text("insert into domains (name, etld1) values (:n, :n) returning id"), {"n": LINK}).scalar()
    persist_result(db, pub, LINK, confirmed(), page(LINK), Enrichment(), evidence_dir=tmp_path, signing_key_hex=KEY)
    set_org_context(db, 1)
    assert db.execute(sa.text("select verdict from email_analyses where id = :i"), {"i": aid}).scalar() == "suspicious"


def test_a_dismissed_link_changes_nothing(db, tmp_path):
    from services.enrich.confirm import ConfirmResult, Signal
    aid, link_id = _cold_email(db)
    persist_result(db, link_id, LINK, ConfirmResult("dismissed", 0.1, [Signal("x", "weak", "y")], 0), page(LINK),
                   Enrichment(), evidence_dir=tmp_path, signing_key_hex=KEY)
    r = db.execute(sa.text("select verdict, rescored_at from email_analyses where id = :i"), {"i": aid}).one()
    assert r.verdict == "suspicious" and r.rescored_at is None


def test_rescore_is_idempotent(db, tmp_path):
    aid, link_id = _cold_email(db)
    for _ in range(2):
        persist_result(db, link_id, LINK, confirmed(), page(LINK), Enrichment(), evidence_dir=tmp_path,
                       signing_key_hex=KEY)
    row = db.execute(sa.text("select signals, verdict_history from email_analyses where id = :i"), {"i": aid}).one()
    assert sum(s["name"] == "link_domain_confirmed" for s in row.signals) == 1 and len(row.verdict_history) == 1
