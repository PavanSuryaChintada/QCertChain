"""End-to-end: a signed-out visitor reads the Technical approach, starts the guided tour, signs in with the read-only
demo key and walks every step to the end, opening the ? panel on each page. Every step must find its element on the
seeded demo, and the tour must change nothing (no request other than GET/HEAD/OPTIONS).

Run through the harness, like test_demo_path.py:  python -m scripts.e2e_stack
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.e2e

CONSOLE = os.environ.get("E2E_CONSOLE_URL", "")
API = os.environ.get("E2E_API_URL", "")
DEMO_KEY = os.environ.get("E2E_KEY_DEMO", "")
LOCAL = {"localhost", "127.0.0.1"}
STEPS = 11

if not (CONSOLE and API and DEMO_KEY):
    pytest.skip("run through scripts/e2e_stack.py (needs E2E_* env)", allow_module_level=True)

from playwright.sync_api import expect, sync_playwright  # noqa: E402


def test_tour_signed_out_to_the_end_with_help_on_every_page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        blocked: list[str] = []

        def offline(route):
            if (urlsplit(route.request.url).hostname or "") in LOCAL:
                route.continue_()
            else:  # the demo must not need the internet
                blocked.append(route.request.url)
                route.abort()

        ctx.route("**/*", offline)
        page = ctx.new_page()
        errors: list[str] = []
        writes: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: writes.append(f"{r.method} {r.url}") if r.method not in ("GET", "HEAD", "OPTIONS") else None)

        # no key yet: the Technical approach is open; the tour asks for a key first
        page.goto(CONSOLE + "/technical")
        expect(page.get_by_role("heading", name="Technical approach", level=1)).to_be_visible(timeout=30_000)
        page.goto(CONSOLE + "/tour")
        expect(page.get_by_test_id("tour-note")).to_be_visible()
        page.get_by_label("API key").fill(DEMO_KEY)
        page.get_by_role("button", name="Sign in").click()

        for n in range(1, STEPS + 1):
            expect(page.get_by_text(f"Step {n} of {STEPS}", exact=True)).to_be_visible(timeout=60_000)
            # every step finds its element on the seeded demo (the card's fallback text must not be what we see)
            expect(page.get_by_test_id("tour-highlight")).to_be_visible(timeout=60_000)
            # the ? explains whichever page this step is on
            page.get_by_test_id("help-button").click()
            help_panel = page.get_by_role("dialog", name=re.compile("^About this page"))
            expect(help_panel.get_by_role("heading", name="What this page is")).to_be_visible()
            help_panel.get_by_role("button", name="Close").click()
            expect(help_panel).to_have_count(0)
            page.get_by_role("button", name="Finish" if n == STEPS else "Next step").click()

        expect(page.get_by_text(f"Step {STEPS} of {STEPS}", exact=True)).to_have_count(0)
        assert not writes, writes
        assert not blocked, blocked
        assert not errors, errors
        browser.close()
