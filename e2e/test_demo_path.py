"""End-to-end: the DEMO.md click-through, in DEMO.md order, in a real browser (A7), with the network cut (A6).

Run through the harness, which stands the whole stack up on LOCAL services only (no Supabase, no internet):
    python -m scripts.e2e_stack
Every request to a host other than localhost is aborted and recorded; the test fails if the console tried one.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.e2e

CONSOLE = os.environ.get("E2E_CONSOLE_URL", "")
API = os.environ.get("E2E_API_URL", "")
KEYS = {k: os.environ.get(f"E2E_KEY_{k.upper()}", "") for k in ("org1", "org2", "demo", "admin")}
ART = Path(os.environ.get("E2E_ARTIFACTS", "e2e/artifacts"))
LOCAL = {"localhost", "127.0.0.1"}

if not (CONSOLE and API and all(KEYS.values())):
    pytest.skip("run through scripts/e2e_stack.py (needs E2E_* env)", allow_module_level=True)

from playwright.sync_api import expect, sync_playwright  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _context(browser, key: str):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    ctx.blocked = []

    def offline(route):
        host = urlsplit(route.request.url).hostname or ""
        if host in LOCAL:
            route.continue_()
        else:  # the demo must not need the internet: record and refuse
            ctx.blocked.append(route.request.url)
            route.abort()
    ctx.route("**/*", offline)
    ctx.add_init_script(f"window.localStorage.setItem('qcertchain.apiKey', {key!r})")
    return ctx


def _shot(page, name):
    ART.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ART / f"{name}.png"))


def _nav(page, label):
    page.get_by_role("link", name=label, exact=True).first.click()


def test_demo_path_in_order_offline(browser):
    t0 = time.monotonic()
    ctx = _context(browser, KEYS["org1"])
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    # 0:00 Architecture
    page.goto(CONSOLE + "/")
    expect(page.get_by_test_id("org-name")).to_contain_text("Bank One SOC", timeout=30_000)
    expect(page.get_by_label("System architecture with live status")).to_be_visible()
    _shot(page, "01-architecture")

    # 0:40 Live queue: rows, and a score breakdown on hover
    _nav(page, "Live queue")
    expect(page.get_by_role("heading", name="Live queue")).to_be_visible()
    first_row = page.locator("table tbody tr").first
    expect(first_row).to_be_visible(timeout=30_000)
    _shot(page, "02-queue")

    # 2:00 Campaigns -> the 470-domain campaign
    _nav(page, "Campaigns")
    page.get_by_role("row").filter(has_text="470").first.click()
    expect(page.get_by_test_id("headline")).to_be_visible(timeout=60_000)

    # 3:00 THE k SLIDER: sweep 1..15, the headline must follow every step (most likely to break silently)
    slider = page.get_by_label("Takedown budget k")
    seen = {}
    lo, hi = int(slider.get_attribute("min")), int(slider.get_attribute("max"))
    assert (lo, hi) == (1, 15), (lo, hi)
    for k in range(lo, hi + 1):
        slider.fill(str(k))
        expect(page.get_by_test_id("headline")).to_contain_text(f"k = {k} ", timeout=5_000)
        txt = page.get_by_test_id("headline").inner_text()
        seen[k] = int(re.search(r"covers ([\d,]+)", txt).group(1).replace(",", ""))
    assert [seen[k] for k in sorted(seen)] == sorted(seen.values()), seen  # more budget never covers less
    assert seen[5] < 470 and seen[15] <= 440                               # a real tradeoff; 30 unreachable
    slider.fill("5")
    expect(page.get_by_test_id("ceiling")).to_contain_text("440")
    expect(page.get_by_test_id("uncoverable-band")).to_be_visible()
    expect(page.get_by_test_id("growth")).to_contain_text("n = 60")
    expect(page.get_by_test_id("scaling-chart")).to_be_visible()
    _shot(page, "03-campaign-k5")

    # 5:00 Solvers: "Run again" re-runs all five solvers live at the slider's k (a NEW computed time, no refusal),
    # and the exhaustive row verifies CP-SAT. The button must carry k = 5: the slider debounce has to settle first.
    run = page.get_by_role("button", name="Run again at k = 5")
    expect(run).to_be_enabled(timeout=30_000)
    caption = page.get_by_text(re.compile(r"(cached result|fresh run) computed")).first
    expect(caption).to_be_visible(timeout=240_000)
    before = caption.inner_text()
    run.click()
    expect(caption).not_to_have_text(before, timeout=240_000)
    expect(caption).to_contain_text("fresh run")
    expect(page.get_by_text(re.compile(r"refused", re.I))).to_have_count(0)
    expect(page.get_by_test_id("verified")).to_be_visible()
    expect(page.get_by_label("Solver benchmark")).to_contain_text("QAOA")
    _shot(page, "04-solvers")

    # 7:00 Evidence: Verify -> Tamper (fails, with the exact mismatch) -> Restore (passes)
    campaign_url = page.url
    page.goto(CONSOLE + "/evidence/" + _first_bundle(page))
    page.get_by_role("button", name="Verify", exact=True).click()
    checks = page.get_by_label("Verification checks")
    expect(checks).to_contain_text("Pass", timeout=60_000)
    expect(checks).not_to_contain_text("Fail")
    page.get_by_role("button", name="Tamper (demo)").click()
    expect(page.get_by_test_id("diff-expected")).to_be_visible(timeout=60_000)
    expect(page.get_by_test_id("diff-found")).to_be_visible()
    expect(checks).to_contain_text("Fail")
    _shot(page, "05-tampered")
    page.get_by_role("button", name="Restore", exact=True).click()
    expect(checks).not_to_contain_text("Fail", timeout=60_000)
    expect(page.get_by_test_id("only-hashes")).to_be_visible()
    _shot(page, "06-restored")

    # 8:20 The second organisation: populated, cannot see org 1, finds org 1's report on the ledger by kit hash
    kit = _kit_hash(page, campaign_url)
    ctx2 = _context(browser, KEYS["org2"])
    p2 = ctx2.new_page()
    p2.goto(campaign_url)
    expect(p2.get_by_text(re.compile(r"not found|does not exist", re.I)).first).to_be_visible(timeout=30_000)
    p2.goto(CONSOLE + "/ledger")
    expect(p2.get_by_test_id("org-name")).to_contain_text("Bank Two SOC", timeout=30_000)
    p2.get_by_label("Kit hash", exact=True).fill(kit)
    p2.get_by_role("button", name="Look up", exact=True).click()
    expect(p2.get_by_text("Bank One SOC").first).to_be_visible(timeout=60_000)
    _shot(p2, "07-org2-ledger")

    # 9:00 Email: the gate is visible
    _nav(page, "Email analyzer")
    page.get_by_label("Raw message or headers").fill(Path("services/email/samples/p01_display_spoof_dmarc_fail.eml")
                                                     .read_text(encoding="utf-8", errors="replace"))
    page.get_by_role("button", name="Analyse").click()
    expect(page.get_by_test_id("gate")).to_contain_text("2 strong required", timeout=60_000)
    _shot(page, "08-email")

    # 10:00 Metrics
    _nav(page, "Metrics")
    expect(page.get_by_test_id("precision")).to_be_visible(timeout=30_000)
    _shot(page, "09-metrics")

    elapsed = time.monotonic() - t0
    print(f"click-through: {elapsed:.0f} s")
    assert not errors, errors[:5]
    assert not ctx.blocked and not ctx2.blocked, ("needed the internet", ctx.blocked[:5] + ctx2.blocked[:5])
    assert elapsed < 12 * 60
    ctx.close()
    ctx2.close()


def _first_bundle(page) -> str:
    import json
    import urllib.request
    req = urllib.request.Request(API + "/campaigns?limit=1", headers={"X-API-Key": KEYS["org1"]})
    cid = json.load(urllib.request.urlopen(req))["items"][0]["id"]
    g = json.load(urllib.request.urlopen(urllib.request.Request(f"{API}/campaigns/{cid}/graph",
                                                                headers={"X-API-Key": KEYS["org1"]})))
    d = json.load(urllib.request.urlopen(urllib.request.Request(f"{API}/domains/{g['domains'][0][0]}",
                                                                headers={"X-API-Key": KEYS["org1"]})))
    return d["evidence_bundle_id"]


def _kit_hash(page, campaign_url: str) -> str:
    import json
    import urllib.request
    cid = campaign_url.rstrip("/").rsplit("/", 1)[-1]
    req = urllib.request.Request(f"{API}/campaigns/{cid}", headers={"X-API-Key": KEYS["org1"]})
    return json.load(urllib.request.urlopen(req))["kit_hash"]


def test_demo_key_click_through_stays_under_its_rate_limit(browser):
    """S5: the published read-only key (60 requests/minute) must not throttle a normal walk through the demo."""
    ctx = _context(browser, KEYS["demo"])
    page = ctx.new_page()
    stamps, throttled = [], []
    page.on("request", lambda r: stamps.append(time.monotonic()) if r.url.startswith(API) else None)
    page.on("response", lambda r: throttled.append(r.url) if r.status == 429 else None)
    page.goto(CONSOLE + "/")
    for label in ("Live queue", "Campaigns", "Ledger", "Metrics", "System health", "Architecture"):
        page.wait_for_timeout(8_000)  # a presenter's pace, with the 5 s polling running
        _nav(page, label)
    page.wait_for_timeout(8_000)
    worst = max(sum(1 for t in stamps if s <= t < s + 60) for s in stamps) if stamps else 0
    print(f"demo key: {len(stamps)} requests, worst 60 s window {worst}")
    assert not throttled, throttled[:3]
    assert worst < 60, worst
    assert not ctx.blocked, ctx.blocked[:5]
    ctx.close()
