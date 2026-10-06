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
from services.enrich.fetch import _icon_url
from services.enrich.fingerprint import favicon_hash
from services.ingest.brands import load_brands

OUT = ROOT / "data/brand_favicons.json"


async def _one(c: httpx.AsyncClient, domain: str) -> str | None:
    for base in (f"https://{domain}/", f"https://www.{domain}/"):
        try:
            r = await c.get(base)
            icon = await c.get(_icon_url(r.text if r.status_code == 200 else "", str(r.url)))
            if icon.status_code == 200 and icon.content and len(icon.content) < 500_000:
                return favicon_hash(icon.content)
        except httpx.HTTPError:
            continue
    return None


async def collect(brands: list[tuple[str, list[str]]], transport: httpx.AsyncBaseTransport | None = None
                  ) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, transport=transport,
                                 headers={"User-Agent": SETTINGS.user_agent}) as c:
        for name, domains in brands:
            hashes = [h for h in await asyncio.gather(*(_one(c, d) for d in domains[:2])) if h]
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
    OUT.write_text(json.dumps(got, indent=1), encoding="utf-8")
    missing = [b.name for b in idx.brands if b.name not in got]
    print(f"favicons for {len(got)}/{len(idx.brands)} brands; unreachable: {missing}")
    sys.exit(0)
