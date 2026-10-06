"""Fetch and observe. Never submit, click or type into a scanned page (TRD §3 Safety).

Playwright (screenshot + rendered DOM) first, httpx fallback (raw HTML, no screenshot -> partial bundle).
Hard timeout, <= 5 redirect hops, honest User-Agent, per-host rate limit via an injected limiter.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urljoin, urlsplit

import httpx

MAX_REDIRECTS = 5
MAX_HTML_BYTES = 2_000_000
MAX_SCRIPT_BYTES = 256_000
MAX_EXTERNAL_SCRIPTS = 5
_ICON = re.compile(r"<link[^>]+rel=[\"']?[^\"'>]*icon[^>]*>", re.I)
_HREF = re.compile(r"href=[\"']?([^\"' >]+)", re.I)
_SCRIPT_SRC = re.compile(r"<script[^>]+src=[\"']?([^\"' >]+)", re.I)


@dataclass
class FetchedPage:
    url: str
    final_url: str
    status: int
    html: str
    headers: dict
    redirect_chain: list[str]
    screenshot: bytes | None
    favicon: bytes | None
    scripts: list[bytes] = field(default_factory=list)
    via: Literal["playwright", "httpx"] = "httpx"


@dataclass
class Unreachable:
    reason: str


@dataclass
class RateLimited:
    host: str


Limiter = Callable[[str], Awaitable[bool]]


def _icon_url(html: str, base: str) -> str:
    m = _ICON.search(html)
    href = _HREF.search(m.group(0)).group(1) if m and _HREF.search(m.group(0)) else "/favicon.ico"
    return urljoin(base, href)


async def _get_small(client: httpx.AsyncClient, url: str, cap: int) -> bytes | None:
    try:
        r = await client.get(url, follow_redirects=True)
        return r.content[:cap] if r.status_code == 200 else None
    except httpx.HTTPError:
        return None


async def fetch_httpx(domain: str, *, timeout_s: float, user_agent: str,
                      transport: httpx.AsyncBaseTransport | None = None) -> FetchedPage | Unreachable:
    start = f"https://{domain}/"
    async with httpx.AsyncClient(timeout=timeout_s, headers={"User-Agent": user_agent}, transport=transport,
                                 follow_redirects=False, verify=False) as client:
        # verify=False: the point is to observe phishing pages, whose TLS may be broken. Nothing is sent.
        url, chain = start, []
        try:
            for _ in range(MAX_REDIRECTS + 1):
                r = await client.get(url)
                if r.is_redirect and "location" in r.headers:
                    chain.append(url)
                    url = urljoin(url, r.headers["location"])
                    if url in chain:
                        return Unreachable(f"redirect loop at {url}")
                    continue
                break
            else:
                return Unreachable(f"more than {MAX_REDIRECTS} redirects")
        except httpx.HTTPError as e:
            return Unreachable(f"{type(e).__name__}: {e}")
        html = r.content[:MAX_HTML_BYTES].decode(r.encoding or "utf-8", errors="replace")
        favicon = await _get_small(client, _icon_url(html, url), 100_000)
        scripts = []
        for src in _SCRIPT_SRC.findall(html)[:MAX_EXTERNAL_SCRIPTS]:
            body = await _get_small(client, urljoin(url, src), MAX_SCRIPT_BYTES)
            if body:
                scripts.append(body)
        return FetchedPage(start, url, r.status_code, html, dict(r.headers), chain, None, favicon, scripts, "httpx")


async def fetch_playwright(domain: str, *, timeout_s: float, user_agent: str) -> FetchedPage | Unreachable:
    from playwright.async_api import Error as PwError
    from playwright.async_api import async_playwright

    start = f"https://{domain}/"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(user_agent=user_agent, ignore_https_errors=True,
                                            java_script_enabled=True, accept_downloads=False)
            page = await ctx.new_page()
            try:
                resp = await page.goto(start, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
            except PwError as e:
                return Unreachable(f"playwright: {str(e).splitlines()[0]}")
            if resp is None:
                return Unreachable("playwright: no response")
            chain, req = [], resp.request.redirected_from
            while req is not None:
                chain.insert(0, req.url)
                req = req.redirected_from
            if len(chain) > MAX_REDIRECTS:
                return Unreachable(f"more than {MAX_REDIRECTS} redirects")
            await page.wait_for_timeout(1500)  # let client-side kits render; never interact
            html = (await page.content())[:MAX_HTML_BYTES]
            shot = await page.screenshot(full_page=True, timeout=int(timeout_s * 1000))
            final = page.url
            headers = await resp.all_headers()
            status = resp.status
        finally:
            await browser.close()
    async with httpx.AsyncClient(timeout=timeout_s, headers={"User-Agent": user_agent}, verify=False) as client:
        favicon = await _get_small(client, _icon_url(html, final), 100_000)
        scripts = [b for src in _SCRIPT_SRC.findall(html)[:MAX_EXTERNAL_SCRIPTS]
                   if (b := await _get_small(client, urljoin(final, src), MAX_SCRIPT_BYTES))]
    return FetchedPage(start, final, status, html, headers, chain, shot, favicon, scripts, "playwright")


async def fetch(domain: str, *, timeout_s: float, user_agent: str, limiter: Limiter | None = None,
                use_playwright: bool = True, transport: httpx.AsyncBaseTransport | None = None
                ) -> FetchedPage | Unreachable | RateLimited:
    host = urlsplit(f"https://{domain}/").hostname or domain
    if limiter is not None and not await limiter(host):
        return RateLimited(host)
    if use_playwright:
        try:
            got = await fetch_playwright(domain, timeout_s=timeout_s, user_agent=user_agent)
            if isinstance(got, FetchedPage):
                return got
        except Exception:  # Playwright missing or browser crashed: httpx path, bundle marked partial
            pass
    return await fetch_httpx(domain, timeout_s=timeout_s, user_agent=user_agent, transport=transport)
