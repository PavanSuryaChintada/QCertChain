"""Brand reference favicons (MODELS.md §3, "ship pHash first"; here the Shodan-convention mmh3 hash).

Fetches each brand's real homepage favicon — observe only — and stores {brand: [favicon_hash]} in
data/brand_favicons.json. A phishing page reusing the stolen favicon then yields the STRONG signal
favicon_brand_match. An unreachable brand is simply absent: no hash is ever guessed. CLIP embeddings are not
built (MODELS.md: only if time; cut first).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

from services.config import ROOT, SETTINGS
from urllib.parse import urljoin

from services.enrich.fetch import _HREF, _ICON
from services.enrich.fingerprint import favicon_hash
from services.ingest.brands import load_brands

OUT = ROOT / "data/brand_favicons.json"


def _icon_urls(html: str, base: str) -> list[str]:
    """Every icon the page declares (icon, shortcut icon, apple-touch-icon, ...) plus /favicon.ico."""
    hrefs = [h.group(1) for m in _ICON.finditer(html) if (h := _HREF.search(m.group(0)))]
    urls = (urljoin(base, h) for h in [*hrefs, "/favicon.ico"] if not h.lower().startswith("data:"))
    return list(dict.fromkeys(u for u in urls if u.startswith(("http://", "https://"))))


async def _one(c: httpx.AsyncClient, domain: str) -> list[str]:
    """Hashes of every icon the brand's real site serves (observed, never guessed). Kits copy whichever they
    scraped, so one hash per brand is not enough."""
    for base in (f"https://{domain}/", f"https://www.{domain}/"):
        try:
            r = await c.get(base)
        except httpx.HTTPError:
            continue
        got = []
        for url in _icon_urls(r.text if r.status_code == 200 else "", str(r.url)):
            try:
                icon = await c.get(url)
            except httpx.HTTPError:
                continue
            if icon.status_code == 200 and icon.content and len(icon.content) < 500_000:
                got.append(favicon_hash(icon.content))
        if got:
            return got
    return []


async def collect(brands: list[tuple[str, list[str]]], transport: httpx.AsyncBaseTransport | None = None
                  ) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, transport=transport,
                                 headers={"User-Agent": SETTINGS.user_agent}) as c:
        for name, domains in brands:
            hashes = [h for hs in await asyncio.gather(*(_one(c, d) for d in domains[:2])) for h in hs]
            if hashes:
                out[name] = sorted(set(hashes))
    return out


def load_brand_favicons(path: Path | str = OUT) -> dict[str, set[str]]:
    p = Path(path)
    if not p.exists():
        return {}
    return {k: set(v) for k, v in json.loads(p.read_text(encoding="utf-8")).items()}


if __name__ == "__main__":
    idx = load_brands(SETTINGS.brands_file)
    got = asyncio.run(collect([(b.name, [d for d in b.legit_domains if d != "google.com"]) for b in idx.brands]))
    # an icon the brand really served earlier stays valid evidence (sites rotate icons; kits keep the old one)
    for name, old in load_brand_favicons().items():
        got[name] = sorted(set(got.get(name, [])) | old)
    OUT.write_text(json.dumps(got, indent=1), encoding="utf-8")
    missing = [b.name for b in idx.brands if b.name not in got]
    print(f"favicons for {len(got)}/{len(idx.brands)} brands; unreachable: {missing}")
    sys.exit(0)
