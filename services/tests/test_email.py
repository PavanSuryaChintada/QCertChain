"""Email-header analysis (spec §3). The gate: malicious needs >= 2 STRONG signals; suspicious is grey.
Recall is MEASURED by scripts/email_eval.py, not asserted here (owner instruction, 2026-10-06)."""
import json
from pathlib import Path

import pytest
import sqlalchemy as sa

from services.config import ROOT, SETTINGS
from services.email.analyze import DomainLookup, analyze
from services.email.parse import parse_email
from services.ingest.brands import load_brands

BR = load_brands(SETTINGS.brands_file)
SAMPLES = ROOT / "services/email/samples"
NONE = lambda d: DomainLookup(None, None, None, None)  # noqa: E731
SPOOF = (SAMPLES / "p01_display_spoof_dmarc_fail.eml").read_bytes()


def names(v):
    return {s.name for s in v.signals}


def test_auth_results_and_received_parsed():
    p = parse_email(SPOOF)
    assert p.auth == {"spf": "fail", "dkim": "none", "dmarc": "fail"}
    assert p.received[0]["ip"] == "203.0.113.9" and p.from_etld1 == "sbi-kyc-update.example"
    assert p.reply_to_etld1 == "sbi-support-desk.example" and p.return_path_etld1 == "bulk-mailer.example"
    assert "https://sbi-kyc-verify-17.example/login" in p.urls


def test_cold_start_spoof_is_suspicious_not_malicious():
    v = analyze(SPOOF, brands=BR, lookup=NONE)
    assert v.verdict == "suspicious" and v.strong_count == 1
    assert {"display_name_brand_spoof", "reply_to_mismatch", "spf_fail", "lookalike_sender_domain"} <= names(v)


def test_confirmed_link_plus_spoof_is_malicious():
    look = lambda d: DomainLookup(7, "confirmed", "c1", "CAMP-0001") if d == "sbi-kyc-verify-17.example" else NONE(d)  # noqa: E731
    v = analyze(SPOOF, brands=BR, lookup=look)
    assert v.verdict == "malicious" and v.strong_count >= 2 and v.linked_campaign_ids == ["c1"]
    assert v.linked_domain_ids == [7]


def test_moderate_only_never_malicious():
    v = analyze((SAMPLES / "p05_paytm_no_display_brand.eml").read_bytes(), brands=BR, lookup=NONE)
    assert v.verdict == "suspicious" and v.strong_count == 0


def test_exact_brand_domain_dmarc_fail_is_strong():
    v = analyze((SAMPLES / "p02_exact_domain_spoof.eml").read_bytes(), brands=BR, lookup=NONE)
    assert "dmarc_fail_brand_from" in names(v)


def test_legit_brand_dmarc_pass_is_clean():
    for f in ("l01_sbi_newsletter.eml", "l02_amazon_order.eml"):
        v = analyze((SAMPLES / f).read_bytes(), brands=BR, lookup=NONE)
        assert v.verdict == "clean", (f, [(s.name, s.detail) for s in v.signals])


def test_legit_never_malicious_even_warm():
    warm = set(json.loads((SAMPLES / "warm_confirmed.json").read_text()))
    look = lambda d: DomainLookup(1, "confirmed", "c", "CAMP") if d in warm else NONE(d)  # noqa: E731
    labels = json.loads((SAMPLES / "labels.json").read_text())
    for f, lab in labels.items():
        if lab["truth"] == "legit":
            assert analyze((SAMPLES / f).read_bytes(), brands=BR, lookup=look).verdict != "malicious", f


@pytest.mark.parametrize("raw", [b"", b"\xff\xfe\x00junk", "just a body with https://x.example",
                                 b"From: =?bad?=\n\nhello", b"From: <<<>>>\nAuthentication-Results: ;;;\n\n",
                                 # review findings, reproduced: naive vs aware Received dates, broken Message-ID
                                 b"From: a@b.example\nReceived: from x by y; Mon, 05 Oct 2026 03:00:00 +0000\n"
                                 b"Received: from p by q; Mon, 05 Oct 2026 02:00:00 -0000\n\nx",
                                 b"From: a@b.example\nReceived: from x by y; Mon, 05 Oct 2026 03:00:00\n"
                                 b"Received: from p by q; Mon, 05 Oct 2026 02:00:00 +0530\n\nx",
                                 b"From: a@b.example\nMessage-ID: <@@@>\n\nx"])
def test_garbage_and_body_only_never_raise(raw):
    v = analyze(raw, brands=BR, lookup=NONE)
    assert v.verdict in {"clean", "suspicious"}


def test_body_only_paste_records_absent_headers():
    p = parse_email((SAMPLES / "p07_body_only_paste.eml").read_bytes())
    assert p.from_addr is None and "From" in p.absent and "Authentication-Results" in p.absent
    assert p.urls == ["https://sbi-kyc-verify-17.example/login"]


def test_folded_headers_parse_identically():
    a, b = parse_email(SPOOF), parse_email((SAMPLES / "p08_folded_headers.eml").read_bytes())
    assert a.auth == b.auth and a.from_etld1 == b.from_etld1 and b.received[0]["ip"] == "203.0.113.9"


def test_non_utf8_bytes_decoded_with_replacement():
    p = parse_email((SAMPLES / "l04_non_utf8_newsletter.eml").read_bytes())
    assert p.from_etld1 == "hdfcbank.com" and "https://www.hdfcbank.com/" in p.urls


def test_signals_carry_details():
    v = analyze(SPOOF, brands=BR, lookup=NONE)
    assert all(s.detail for s in v.signals)


@pytest.mark.db
def test_persist_creates_candidates_never_confirmed(db):
    from services.email.analyze import db_lookup, persist_and_correlate
    v = analyze(SPOOF, brands=BR, lookup=db_lookup(db))
    aid, new_ids = persist_and_correlate(db, v, "analyst")
    rows = db.execute(sa.text("select name, status, source from domains order by name")).all()
    assert rows and all(r.status == "candidate" and r.source == "email" for r in rows)
    assert {r.name for r in rows} >= {"sbi-kyc-update.example", "sbi-kyc-verify-17.example"}
    assert len(new_ids) == len(rows)
    a = db.execute(sa.text("select verdict, strong_count, source from email_analyses where id=:i"), {"i": aid}).one()
    assert a.verdict == "suspicious" and a.strong_count == 1 and a.source == "analyst"


@pytest.mark.db
def test_api_analyze_json_multipart_and_limits(api):
    r = api.post("/email/analyze", json={"raw": SPOOF.decode(), "source": "sample"})
    assert r.status_code == 200 and r.json()["verdict"] == "suspicious" and r.json()["new_candidate_ids"]
    r2 = api.post("/email/analyze", files={"eml": ("x.eml", SPOOF, "message/rfc822")})
    assert r2.status_code == 200 and r2.json()["source"] == "analyst"
    big = api.post("/email/analyze", json={"raw": "x" * (2 * 1024 * 1024 + 1)})
    assert big.status_code == 413
    listed = api.get("/email/analyses?verdict=suspicious").json()
    assert listed["total"] == 2 and api.get(f"/email/analyses/{r.json()['id']}").json()["id"] == r.json()["id"]


def test_display_name_matching_ignores_spacing_and_punctuation():
    from services.email.signals import _brand_in_display
    assert _brand_in_display("Income Tax Department", BR).name == "Income Tax India"
    assert _brand_in_display("H.D.F.C. Bank Alerts", BR).name == "HDFC Bank"
    assert _brand_in_display("Priya", BR) is None
    assert _brand_in_display("Service desk", BR) is None  # 'vi' inside a word is not Vodafone Idea


@pytest.mark.db
def test_api_rejects_non_object_json_with_422(api):
    for body in ("[]", '"x"', "42"):
        r = api.post("/email/analyze", content=body, headers={"content-type": "application/json"})
        assert r.status_code == 422, (body, r.status_code)


def test_fuzzed_headers_never_raise():
    """5,000 malformed messages (fixed seed). Found 86 stdlib structured-parser crashes before the fix."""
    import random
    rng = random.Random(1)
    heads = ["From", "Reply-To", "Return-Path", "Message-ID", "Authentication-Results", "Received",
             "Received-SPF", "Date", "Subject", "DKIM-Signature", "Content-Type"]
    vals = ["<@@@>", "", "=?utf-8?B?????=", "a@", "@b", "<<>>", "x" * 3000, "Mon, 99 Foo 2026 25:61:61 +9999",
            "multipart/mixed; boundary=", "\x00\x01", "é漢字", "a@b.example (c) <d@e>", "; ; ;", "spf=",
            "from [999.1.1.1] by ;", "\t\tfolded\n continued"]
    for _ in range(5000):
        lines = [f"{rng.choice(heads)}: {rng.choice(vals)}{rng.choice(vals)}" for _ in range(rng.randint(0, 8))]
        raw = ("\n".join(lines) + "\n\n" + rng.choice(["https://x.example/a", "", "<a href='http://y.example'>"])
               ).encode("utf-8", "replace")
        if rng.random() < 0.3:
            raw = bytes(rng.randrange(256) for _ in range(rng.randint(0, 200))) + raw
        analyze(raw, brands=BR, lookup=NONE)
