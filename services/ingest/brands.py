"""Brand list, allowlist and the shared eTLD+1 extractor."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import tldextract
import yaml

from services.config import ROOT

# Offline PSL snapshot, PRIVATE section included: x.github.io / x.vercel.app are their own
# registrable domains. Without it every GitHub Pages phish collapses into "github.io".
# data/shared_hosting.txt adds hosting platforms missing from the PSL (weebly.com, ...).
_SHARED_HOSTING = [ln.strip() for ln in (ROOT / "data/shared_hosting.txt").read_text(encoding="utf-8").splitlines()
                   if ln.strip() and not ln.startswith("#")]
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), include_psl_private_domains=True,
                                 extra_suffixes=_SHARED_HOSTING)

# Infrastructure that is never a phishing target itself. Registry-restricted zones too:
# bank.in is reserved by RBI/IDRBT for regulated banks.
INFRA_ALLOW = ["cloudflare.com", "amazonaws.com", "azureedge.net", "googleusercontent.com",
               "akamaiedge.net", "fastly.net", "cloudfront.net", "bank.in"]


@lru_cache(maxsize=200_000)
def etld1(name: str) -> str:
    """Registrable domain; falls back to the name itself when it is a bare public suffix."""
    r = _EXTRACT(name)
    return r.top_domain_under_public_suffix if hasattr(r, "top_domain_under_public_suffix") and r.top_domain_under_public_suffix \
        else (r.registered_domain or name)


@dataclass(frozen=True)
class Brand:
    name: str
    tokens: tuple[str, ...]
    legit_domains: tuple[str, ...]
    sector: str
    legit_tlds: tuple[str, ...] = ()


@dataclass
class BrandIndex:
    brands: list[Brand]
    legit_etld1s: set[str] = field(default_factory=set)
    legit_tlds: set[str] = field(default_factory=set)
    by_token: dict[str, Brand] = field(default_factory=dict)
    tokens_by_len: dict[int, list[str]] = field(default_factory=lambda: defaultdict(list))


def load_brands(path: str | Path) -> BrandIndex:
    p = Path(path)
    raw = yaml.safe_load((p if p.is_absolute() else ROOT / p).read_text(encoding="utf-8"))
    idx = BrandIndex(brands=[])
    for b in raw:
        brand = Brand(b["name"], tuple(t.lower() for t in b["tokens"]),
                      tuple(d.lower() for d in b["legit_domains"]), b["sector"],
                      tuple(t.lower() for t in b.get("legit_tlds", ())))
        idx.brands.append(brand)
        idx.legit_etld1s.update(etld1(d) for d in brand.legit_domains)
        idx.legit_tlds.update(brand.legit_tlds)
        for t in brand.tokens:
            if t in idx.by_token:
                raise ValueError(f"token {t!r} used by two brands")
            idx.by_token[t] = brand
            idx.tokens_by_len[len(t)].append(t)
    return idx


def load_allowlist(path: str | Path, brands: BrandIndex) -> frozenset[str]:
    p = Path(path)
    p = p if p.is_absolute() else ROOT / p
    out: set[str] = set(brands.legit_etld1s) | set(INFRA_ALLOW)
    for line in p.read_text(encoding="utf-8").splitlines():
        d = line.strip().lower()
        if not d:
            continue
        r = _EXTRACT(d)
        if r.registered_domain:  # a bare public suffix (github.io) has none and is skipped
            out.add(etld1(d))
    return frozenset(out)
