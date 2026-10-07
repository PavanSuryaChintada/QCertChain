"""persist_result: everything that happens after a verdict, in one transaction."""
from datetime import datetime, timezone
from pathlib import Path

import nacl.signing
import pytest
import sqlalchemy as sa

from services.api import repo
from services.api.pipeline import persist_result
from services.enrich.confirm import ConfirmResult, Signal
from services.enrich.enrichers import Enrichment
from services.enrich.fetch import FetchedPage
from services.ingest.triage import triage

pytestmark = pytest.mark.db
KEY = nacl.signing.SigningKey.generate().encode().hex()
KIT = (Path(__file__).parent / "fixtures/kit_a.html").read_text(encoding="utf-8")


def candidate(db, name):
    t = triage(name)
    return repo.upsert_candidate(db, name=name, etld1=t.etld1, cert_id=None, triage=t, source="certstream",
                                 ct_seen_at=datetime.now(timezone.utc))[0]


def confirmed():
    return ConfirmResult("confirmed", 0.9, [Signal("credential_post_foreign_origin", "strong", "POST -> 203.0.113.9"),
                                             Signal("kit_dom_hash_match", "strong", "kit")], 2)


def page(name):
    return FetchedPage(f"https://{name}/", f"https://{name}/", 200, KIT, {"server": "nginx"}, [], b"PNG", None, [],
                       "playwright")


def test_confirmed_persists_enrichment_edges_bundle_report_anchor(db, tmp_path):
    d = candidate(db, "sbi-verify-kyc.top")
    e = Enrichment(ip_addresses=["203.0.113.9"], nameservers=["ns1.x.example"], registrar="Registrar A",
                   abuse_email="abuse@registrar-a.example", dom_hash="deadbeef", cert_pem="-----BEGIN CERTIFICATE-----")
    bundle_id = persist_result(db, d, "sbi-verify-kyc.top", confirmed(), page("sbi-verify-kyc.top"), e,
                               evidence_dir=tmp_path, signing_key_hex=KEY)
    assert bundle_id
    assert db.execute(sa.text("select status from org_domains where id=:d"), {"d": d}).scalar() == "confirmed"
    kinds = {r.kind for r in db.execute(sa.text("select n.kind from graph_edges e join infra_nodes n on n.id=e.node_id"))}
    assert kinds == {"ip", "nameserver", "registrar", "kit_hash"}
    b = db.execute(sa.text("select partial, artifact_dir from evidence_bundles where id=:b"), {"b": bundle_id}).one()
    assert b.partial is False and Path(b.artifact_dir, "screenshot.png").exists()
    names = set(db.execute(sa.text("select name from evidence_artifacts where bundle_id=:b"), {"b": bundle_id}).scalars())
    assert {"dom.html", "headers.json", "screenshot.png", "cert.pem", "dns.json", "whois.json", "asn.json",
            "kit.json", "meta.json"} <= names
    rep = db.execute(sa.text("select recipient, sent, body from abuse_reports where bundle_id=:b"), {"b": bundle_id}).one()
    assert rep.recipient == "abuse@registrar-a.example" and rep.sent is False and "not sent" in rep.body
    assert db.execute(sa.text("select kind from anchor_queue")).scalar() == "evidence"
    assert repo.known_kits(db).get("deadbeef")


def test_unreachable_persists_status_only(db, tmp_path):
    d = candidate(db, "dead-sbi-kyc.top")
    r = ConfirmResult("unreachable", 0.0, [Signal("not_assessable", "weak", "timeout")], 0)
    assert persist_result(db, d, "dead-sbi-kyc.top", r, None, Enrichment(), evidence_dir=tmp_path,
                          signing_key_hex=KEY) is None
    assert db.execute(sa.text("select status from org_domains where id=:d"), {"d": d}).scalar() == "unreachable"
    assert db.execute(sa.text("select count(*) from evidence_bundles")).scalar() == 0


def test_bundle_without_screenshot_is_partial(db, tmp_path):
    d = candidate(db, "nosshot-sbi-kyc.top")
    p = FetchedPage("https://nosshot-sbi-kyc.top/", "https://nosshot-sbi-kyc.top/", 200, KIT, {}, [], None, None, [],
                    "httpx")
    b = persist_result(db, d, "nosshot-sbi-kyc.top", confirmed(), p, Enrichment(dom_hash="x"), evidence_dir=tmp_path,
                       signing_key_hex=KEY)
    assert db.execute(sa.text("select partial from evidence_bundles where id=:b"), {"b": b}).scalar() is True
