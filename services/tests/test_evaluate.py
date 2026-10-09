"""The report must never state a number that was not measured."""
import pytest

from scripts.evaluate import pct, section


def test_failed_section_is_unavailable_not_a_number():
    @section
    def broken():
        raise ConnectionError("crt.sh unreachable")
    out = broken()
    assert set(out) == {"unavailable", "trace"} and "crt.sh unreachable" in out["unavailable"]


def test_percentiles():
    assert pct([], .5) is None
    assert pct([1, 2, 3, 4, 5], .5) == 3 and pct([1, 2, 3, 4, 100], .95) == 100


def test_no_balanced_precision_anywhere():
    src = open("scripts/evaluate.py", encoding="utf-8").read()
    assert "balanced" not in src.replace("Balanced-set precision is never computed", "")


def test_confirmation_eval_covers_modern_js_kits(monkeypatch):
    """S3d: the labelled set must exercise the code that ships (JS-era kits), and report each family separately so a
    blind spot (same-origin relay) shows as a number instead of disappearing into an average."""
    import dataclasses

    from scripts import evaluate
    from services.enrich import confirm
    monkeypatch.setattr(confirm, "SETTINGS", dataclasses.replace(confirm.SETTINGS, exfil_signal_strength="strong",
                                                                 js_post_signal_strength="strong"))
    out = evaluate.confirmation()
    fam = out["by_family"]
    assert fam["modern_js_kit"]["n"] == 7 and fam["modern_js_legit"]["n"] == 2
    assert out["per_page"]["pJ0"] == "confirmed"           # Telegram exfil + a POST to a different site
    assert out["per_page"]["pJ5"] == "candidate"           # same-origin relay: invisible to any browser-side check
    assert out["per_page"]["pJ6"] == "candidate"           # one Telegram endpoint seen twice is one signal (S3b)
    assert out["false_confirmations_of_legit_pages"] == 0


@pytest.mark.db
def test_response_time_counts_each_live_domain_once_with_the_verdict_of_whoever_checked_it(db):
    """Spec 2026-10-09 §5: a live candidate is checked by the organisation that owns its sector. Each domain counts
    once, with that organisation's verdict, not once per organisation that can see the shared feed."""
    from datetime import datetime, timezone

    import sqlalchemy as sa

    from scripts import evaluate
    from services.api import repo
    from services.ingest.triage import triage
    shop = db.execute(sa.text("insert into organisations (slug, name, category) values ('shopsafe', 'ShopSafe', 'ecommerce') "
                              "returning id")).scalar()
    ids = {}
    for n in ("sbi-verify-kyc.top", "amazon-login-verify.top"):
        t = triage(n)
        ids[n], _ = repo.upsert_candidate(db, name=n, etld1=t.etld1, cert_id=None, triage=t, source="certstream",
                                          ct_seen_at=datetime.now(timezone.utc))
    for org, n, status in ((1, "sbi-verify-kyc.top", "unreachable"), (shop, "amazon-login-verify.top", "dismissed")):
        db.execute(sa.text("""insert into domain_verdicts (org_id, domain_id, status, verdict_at)
                              values (:o, :d, :s, now() + interval '5 seconds')"""), {"o": org, "d": ids[n], "s": status})
    out = evaluate.response_time(None, conn=db)
    assert "unavailable" not in out, out
    assert out["verdicts_from_live_candidates"] == {"unreachable": 1, "dismissed": 1}
    assert out["candidate_to_verdict_s"]["n"] == 2
    assert out["ct_seen_to_candidate_s"]["n"] == 2
