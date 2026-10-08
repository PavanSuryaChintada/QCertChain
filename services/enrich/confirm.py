"""Confirmation: evidence, not prediction (TRD §3, MODELS §5).

confirmed  <=>  at least TWO INDEPENDENT STRONG signals. Never one. Never a moderate-only combination.
Independent (S3b, one rule for every signal): from different detectors AND resting on different artifacts (the
destination site a credential goes to, the page's DOM hash, its favicon hash). One observation seen by two detectors,
such as a POST to api.telegram.org seen by S1 and by S2, is ONE piece of evidence. The database enforces the same rule
(has_two_independent_strong in schema.sql).
Every verdict carries the signals that produced it; the UI and the abuse report show them verbatim.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

import asyncio

from services.config import SETTINGS
from services.enrich.enrichers import Enrichment, enrich
from services.enrich.exfil import exfil_endpoints, foreign_post_endpoints
from services.enrich.fetch import FetchedPage, Limiter, RateLimited, Unreachable, fetch
from services.enrich.fingerprint import (extract_forms, favicon_hash, js_bundle_hashes,
                                         kit_hash, page_title)
from services.ingest.brands import Brand, etld1

Strength = Literal["strong", "moderate", "weak"]
Verdict = Literal["confirmed", "dismissed", "unreachable", "candidate"]

PARKED = ("domain is for sale", "this domain may be for sale", "buy this domain", "parked free",
          "domain parking", "sedoparking", "parkingcrew", "hugedomains", "dan.com", "is parked")
# A hosting provider's own phishing warning replaces the page: the content is not visible to us, so it is not
# assessable (still a candidate, rechecked), never a dismissal. Nor is it our evidence for a confirmation.
INTERSTITIALS = ("suspected phishing | cloudflare", "suspected phishing site ahead", "phishing warning | cloudflare")
FREE_CAS = ("let's encrypt", "zerossl")
_OBFUSCATION = re.compile(r"\beval\s*\(|\batob\s*\(|\bunescape\s*\(|String\.fromCharCode\s*\(|\\x[0-9a-f]{2}(\\x[0-9a-f]{2}){20}", re.I)
_B64_BLOB = re.compile(r"[A-Za-z0-9+/]{2048,}={0,2}")
_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.I | re.S)
_PASSWORD = re.compile(r"<input[^>]+type=[\"']?password", re.I)


@dataclass
class Signal:
    name: str
    strength: Strength
    detail: str
    artifacts: tuple[str, ...] = ()   # what the signal rests on: "endpoint:<site>", "dom:<hash>", "favicon:<hash>"


MAX_INSTANCES = 3  # per detector: a few distinct artifacts are enough to find an independent pairing


def independent_strong(signals: list[Signal]) -> int:
    """The largest set of strong signals from DIFFERENT detectors whose artifacts are pairwise disjoint (S3b).
    Exact (all subsets): at most a handful of strong signals exist per page."""
    strong = [s for s in signals if s.strength == "strong"]
    best = 0
    for mask in range(1, 1 << len(strong)):
        pick = [s for i, s in enumerate(strong) if mask >> i & 1]
        if len(pick) <= best or len({s.name for s in pick}) < len(pick):
            continue
        arts = [a for s in pick for a in set(s.artifacts)]
        if len(set(arts)) == len(arts):
            best = len(pick)
    return best


@dataclass
class ConfirmResult:
    verdict: Verdict
    confidence: float
    signals: list[Signal] = field(default_factory=list)
    strong_count: int = 0

    def reasons(self) -> dict:
        """strong_count is the INDEPENDENT count (S3b); each signal lists the artifacts it rests on."""
        return {"verdict": self.verdict, "confidence": self.confidence, "strong_count": self.strong_count,
                "signals": [{**s.__dict__, "artifacts": list(s.artifacts)} for s in self.signals]}


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _site(host: str) -> str:
    # IP literals and bare hosts are their own "site"
    return host if not host or host.replace(".", "").isdigit() or ":" in host else etld1(host)


def analyze_page(page: FetchedPage, domain: str, brand: Brand | None, known_kits: dict[str, str],
                 brand_favicons: dict[str, set[str]], registered_at: datetime | None, issuer: str | None,
                 now: datetime | None = None, signal_strengths: dict[str, str] | None = None) -> ConfirmResult:
    """Pure function over an observed page. Used by live confirmation and by the labelled seed."""
    now = now or datetime.now(timezone.utc)
    html = page.html or ""
    low = html.lower()
    title = page_title(html) or ""
    if any(p in low for p in INTERSTITIALS):
        return ConfirmResult("unreachable", 0.0, [Signal("not_assessable", "weak",
                             f"HTTP {page.status}; hosting provider's phishing interstitial hides the page — "
                             "still a candidate")], 0)
    if any(p in low for p in PARKED) or (page.status >= 400 and len(html) < 512):
        return ConfirmResult("unreachable", 0.0, [Signal("not_assessable", "weak",
                             f"HTTP {page.status}; parked or error page — still a candidate")], 0)

    signals: list[Signal] = []
    page_site = _site(_host(page.final_url))
    legit = set(brand.legit_domains) if brand else set()
    legit_sites = {etld1(d) for d in legit}
    forms = extract_forms(html, page.final_url)

    # ---- strong ---------------------------------------------------------------------------------
    for f in forms:
        if not f.has_password:
            continue
        target = _host(f.action_url)
        if target and _site(target) != page_site and _site(target) not in legit_sites:
            brand_txt = f" (not {sorted(legit)[0]})" if legit else ""
            signals.append(Signal("credential_post_foreign_origin", "strong",
                                  f"form {f.method.upper()} with password field -> {target}{brand_txt}",
                                  (f"endpoint:{_site(target)}",)))
            break
    dom = kit_hash(html)
    if dom is not None and dom in known_kits:
        signals.append(Signal("kit_dom_hash_match", "strong",
                              f"DOM structure {dom[:12]}... matches known kit {known_kits[dom]}", (f"dom:{dom}",)))
    if brand and page.favicon and favicon_hash(page.favicon) in brand_favicons.get(brand.name, set()):
        fh = favicon_hash(page.favicon)
        signals.append(Signal("favicon_brand_match", "strong", f"favicon mmh3 {fh} equals {brand.name}'s real favicon",
                              (f"favicon:{fh}",)))

    # ---- S1/S2: credential exfiltration in the rendered DOM + the kit's JS (strength set by the S3 gate) ------
    st = signal_strengths if signal_strengths is not None else {
        "exfil": SETTINGS.exfil_signal_strength, "js_post": SETTINGS.js_post_signal_strength}
    if st.get("exfil", "off") != "off" or st.get("js_post", "off") != "off":
        scripts_src = [(u, b.decode("utf-8", "replace")) for u, b in page.bundles] or             [(f"script#{i}", b.decode("utf-8", "replace")) for i, b in enumerate(page.scripts)]
        if st.get("exfil", "off") != "off":
            seen: set[str] = set()
            for h in exfil_endpoints(html, scripts_src):
                art = f"endpoint:{_site(h.match.split('/')[0].lower())}"
                if art not in seen and len(seen) < MAX_INSTANCES:
                    seen.add(art)
                    signals.append(Signal("credential_exfil_endpoint", st["exfil"],
                                          f"credential page references {h.kind}: {h.match[:120]} (in {h.where[:120]})",
                                          (art,)))
        if st.get("js_post", "off") != "off":
            for h in foreign_post_endpoints(html, scripts_src, page.final_url, legit_sites)[:MAX_INSTANCES]:
                signals.append(Signal("credential_post_foreign_origin_js", st["js_post"],
                                      f"credential page's code POSTs to {h.origin} ({h.match[:120]}, in {h.where[:120]})",
                                      (f"endpoint:{_site(_host(h.origin))}",)))

    # ---- moderate -------------------------------------------------------------------------------
    if brand and page_site not in legit_sites:
        t = title.lower()
        hit = next((x for x in (brand.name.lower(), *brand.tokens) if len(x) > 3 and x in t), None)
        if hit:
            signals.append(Signal("title_impersonates_brand", "moderate", f"title '{title[:80]}' names {brand.name}"))
    scripts = [s.decode("utf-8", "replace") for s in page.scripts] + _INLINE_SCRIPT.findall(html)
    obf = next((m.group(0)[:40] for s in scripts for m in [_OBFUSCATION.search(s) or _B64_BLOB.search(s)] if m), None)
    if obf:
        signals.append(Signal("obfuscated_js", "moderate", f"script contains {obf!r}"))
    if _PASSWORD.search(html):
        signals.append(Signal("password_field_present", "moderate", "page asks for a password"))

    # ---- weak -----------------------------------------------------------------------------------
    if registered_at and (now - registered_at).days < 30:
        signals.append(Signal("recently_registered", "weak", f"registered {(now - registered_at).days} days ago"))
    if issuer and issuer.lower().startswith(FREE_CAS):
        signals.append(Signal("issuer_is_free_ca", "weak", f"certificate issued by {issuer}"))

    strong = independent_strong(signals)   # S3b: independent evidence, not a count of labels
    moderate = sum(s.strength == "moderate" for s in signals)
    weak = sum(s.strength == "weak" for s in signals)
    if strong >= 2:
        verdict: Verdict = "confirmed"
    elif strong == 0 and moderate == 0:
        verdict = "dismissed"  # weak-only (free CA, young domain) describes half the internet
    else:
        verdict = "candidate"  # insufficient evidence — still a candidate
    confidence = round(min(0.99, 0.5 + 0.2 * strong + 0.08 * moderate + 0.02 * weak), 2) if signals else 0.0
    return ConfirmResult(verdict, confidence, signals, strong)


async def confirm(domain: str, brand: Brand | None, *, known_kits: dict[str, str],
                  brand_favicons: dict[str, set[str]], issuer: str | None, limiter: Limiter | None = None,
                  use_playwright: bool = True, now: datetime | None = None,
                  signal_strengths: dict[str, str] | None = None
                  ) -> tuple[ConfirmResult, FetchedPage | None, Enrichment]:
    """candidate -> confirmed | dismissed | unreachable | candidate (insufficient evidence / rate limited).
    The page fetch and the DNS/RDAP/TLS/ASN lookups run concurrently (< 20 s budget, CLAUDE.md §5)."""
    got, e = await asyncio.gather(
        fetch(domain, timeout_s=SETTINGS.confirm_timeout_s, user_agent=SETTINGS.user_agent, limiter=limiter,
              use_playwright=use_playwright),
        enrich(domain, None))
    if isinstance(got, RateLimited):
        return ConfirmResult("candidate", 0.0, [Signal("rate_limited", "weak",
                             f"per-host rate limit on {got.host}; not fetched, retry later")], 0), None, e
    if isinstance(got, Unreachable):
        return ConfirmResult("unreachable", 0.0, [Signal("not_assessable", "weak",
                             f"could not fetch: {got.reason} — still a candidate")], 0), None, e
    e.dom_hash = kit_hash(got.html)
    e.favicon_hash = favicon_hash(got.favicon) if got.favicon else None
    e.js_hashes = js_bundle_hashes(got.scripts)
    e.page_title = page_title(got.html)
    if got.screenshot is None:
        e.partial = True
        e.errors.setdefault("screenshot", f"fetched via {got.via}; no screenshot")
    result = analyze_page(got, domain, brand, known_kits, brand_favicons, e.registered_at,
                          issuer or e.cert_issuer, now=now, signal_strengths=signal_strengths)
    return result, got, e
