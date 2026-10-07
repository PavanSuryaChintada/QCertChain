"""Fetch and observe. Never submit, click or type into a scanned page (TRD §3 Safety).

Playwright (screenshot + rendered DOM) first, httpx fallback (raw HTML, no screenshot -> partial bundle).
Hard timeout, <= 5 redirect hops, honest User-Agent, per-host rate limit via an injected limiter.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
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


Resolver = Callable[[str], Awaitable[list[str]]]


def is_public_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_global and not (a.is_multicast or a.is_reserved or a.is_loopback or a.is_link_local)


async def resolve_host(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({i[4][0] for i in infos})


async def _block_reason(url: str, resolve: Resolver) -> str | None:
    """SSRF guard: the host comes from an attacker's certificate and DNS. Every address it resolves to must
    be public — no loopback, private, link-local (cloud metadata) or internal service names. Returns None when
    the fetch may proceed, else why not. Fails closed; a name that does not resolve is reported as a DNS failure,
    not as a non-public address, so the unreachable breakdown is honest."""
    host = urlsplit(url).hostname
    if not host:
        return "blocked: no host"
    try:
        ips = [host] if _is_ip(host) else await resolve(host)
    except Exception as e:
        return f"dns: {host} does not resolve ({type(e).__name__})"
    if not ips:
        return f"dns: {host} has no addresses"
    if not all(is_public_ip(i) for i in ips):
        return f"blocked: {host} resolves to a non-public address"
    return None


async def _public(url: str, resolve: Resolver) -> bool:
    return await _block_reason(url, resolve) is None


def _is_ip(h: str) -> bool:
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


async def _get_capped(client: httpx.AsyncClient, url: str, cap: int) -> httpx.Response:
    """Stream the body and stop at `cap` bytes: a huge or trickling response must not exhaust memory."""
    async with client.stream("GET", url) as r:
        buf = bytearray()
        async for chunk in r.aiter_bytes():
            buf += chunk
            if len(buf) >= cap:
                break
        r._content = bytes(buf[:cap])  # noqa: SLF001 — finalise a capped body
        return r


async def _get_small(client: httpx.AsyncClient, url: str, cap: int, resolve: Resolver) -> bytes | None:
    try:
        for _ in range(MAX_REDIRECTS + 1):
            if not await _public(url, resolve):
                return None
            r = await _get_capped(client, url, cap)
            if r.is_redirect and "location" in r.headers:
                url = urljoin(url, r.headers["location"])
                continue
            return r.content if r.status_code == 200 else None
    except httpx.HTTPError:
        return None
    return None


async def fetch_httpx(domain: str, *, timeout_s: float, user_agent: str,
                      transport: httpx.AsyncBaseTransport | None = None,
                      resolve: Resolver | None = None) -> FetchedPage | Unreachable:
    resolve = resolve or resolve_host
    try:
        return await asyncio.wait_for(_fetch_httpx(domain, timeout_s, user_agent, transport, resolve),
                                      timeout=timeout_s * 2)  # overall deadline: httpx timeouts are per read
    except asyncio.TimeoutError:
        return Unreachable(f"no complete response within {timeout_s * 2:.0f} s")


async def _fetch_httpx(domain, timeout_s, user_agent, transport, resolve) -> FetchedPage | Unreachable:
    start = f"https://{domain}/"
    async with httpx.AsyncClient(timeout=timeout_s, headers={"User-Agent": user_agent}, transport=transport,
                                 follow_redirects=False, verify=False) as client:
        # verify=False: the point is to observe phishing pages, whose TLS may be broken. Nothing is sent.
        url, chain = start, []
        try:
            for _ in range(MAX_REDIRECTS + 1):
                if why := await _block_reason(url, resolve):
                    return Unreachable(why)
                r = await _get_capped(client, url, MAX_HTML_BYTES)
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
        html = r.content[:MAX_HTML_BYTES].decode(r.encoding or "utf-8", errors="replace")[:MAX_HTML_BYTES]
        favicon = await _get_small(client, _icon_url(html, url), 100_000, resolve)
        scripts = []
        for src in _SCRIPT_SRC.findall(html)[:MAX_EXTERNAL_SCRIPTS]:
            body = await _get_small(client, urljoin(url, src), MAX_SCRIPT_BYTES, resolve)
            if body:
                scripts.append(body)
        return FetchedPage(start, url, r.status_code, html, dict(r.headers), chain, None, favicon, scripts, "httpx")


async def fetch_playwright(domain: str, *, timeout_s: float, user_agent: str,
                           resolve: Resolver | None = None) -> FetchedPage | Unreachable:
    from playwright.async_api import Error as PwError
    from playwright.async_api import async_playwright

    resolve = resolve or resolve_host
    start = f"https://{domain}/"
    if why := await _block_reason(start, resolve):
        return Unreachable(why)
    blocked: list[str] = []

    async def guard(route):  # every request the page makes, redirects included, passes the SSRF guard
        if await _public(route.request.url, resolve):
            await route.continue_()
        else:
            blocked.append(route.request.url)
            await route.abort("blockedbyclient")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(user_agent=user_agent, ignore_https_errors=True,
                                            java_script_enabled=True, accept_downloads=False)
            page = await ctx.new_page()
            await page.route("**/*", guard)
            try:
                resp = await page.goto(start, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
            except PwError as e:
                if blocked:  # the navigation itself (or a redirect hop) hit the guard
                    return Unreachable(f"blocked: {urlsplit(blocked[0]).hostname} is a non-public address")
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
        favicon = await _get_small(client, _icon_url(html, final), 100_000, resolve)
        scripts = [b for src in _SCRIPT_SRC.findall(html)[:MAX_EXTERNAL_SCRIPTS]
                   if (b := await _get_small(client, urljoin(final, src), MAX_SCRIPT_BYTES, resolve))]
    return FetchedPage(start, final, status, html, headers, chain, shot, favicon, scripts, "playwright")


async def fetch(domain: str, *, timeout_s: float, user_agent: str, limiter: Limiter | None = None,
                use_playwright: bool = True, transport: httpx.AsyncBaseTransport | None = None,
                resolve: Resolver | None = None) -> FetchedPage | Unreachable | RateLimited:
    host = urlsplit(f"https://{domain}/").hostname or domain
    if limiter is not None and not await limiter(host):
        return RateLimited(host)
    if use_playwright:
        try:
            # A site Playwright could not reach is unreachable for httpx too: retrying only doubled the wait
            # (measured p95 candidate->verdict 44.7 s). Return Playwright's verdict, page or Unreachable.
            return await fetch_playwright(domain, timeout_s=timeout_s, user_agent=user_agent, resolve=resolve)
        except Exception:  # Playwright itself missing or crashed: httpx path, bundle marked partial
            pass
    return await fetch_httpx(domain, timeout_s=timeout_s, user_agent=user_agent, transport=transport, resolve=resolve)
