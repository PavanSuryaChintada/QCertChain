"""Triage — the hot path. Produces a CANDIDATE score, never a verdict (TRD §2, MODELS §0).

Allowlist first, always. Rule weights are TRD §2's and are not tuned here.
Decisions recorded with the owner (2026-10-06):
- Lookalike uses Damerau-Levenshtein only for tokens of >= 5 chars (<= 1 edit for 5-7, <= 2 for 8+).
  A flat <= 2 on 3-4 letter tokens matches most short words.
- Tokens of <= 3 chars count only as a whole hyphen/dot/digit-delimited segment.
- "Free CA + new domain" never fires here: age needs WHOIS, which MODELS §2 keeps out of the
  5 ms budget. It is a weak signal in confirmation instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from services.config import SETTINGS
from services.ingest.brands import BrandIndex, load_allowlist, load_brands
from services.ml.features import Features, extract

W_BRAND, W_LOOKALIKE, W_HOMOGLYPH, W_TLD, W_KEYWORD, W_SHAPE = 0.35, 0.30, 0.30, 0.15, 0.15, 0.10


@dataclass
class Reason:
    feature: str
    value: object
    contribution: float


@dataclass
class TriageResult:
    score: float
    is_candidate: bool
    etld1: str
    brand: str | None
    reasons: list[Reason] = field(default_factory=list)
    provenance: Literal["rules", "model"] = "rules"
    threshold: float = SETTINGS.triage_threshold


@lru_cache(maxsize=1)
def _brands() -> BrandIndex:
    return load_brands(SETTINGS.brands_file)


@lru_cache(maxsize=1)
def _allow() -> frozenset[str]:
    return load_allowlist(SETTINGS.allowlist_file, _brands())


def warm() -> None:
    """Load brands, allowlist and matchers now. Workers call this at startup: the lazy
    allowlist build takes seconds and must never land on the first live certificate."""
    _brands()
    _allow()
    triage("warm-up-sbi-kyc.example.com")


def score_rules(f: Features) -> list[Reason]:
    reasons: list[Reason] = []
    if f.brand_token_exact:
        reasons.append(Reason("brand_token_exact", f.matched_token, W_BRAND))
    if f.lookalike_token:
        reasons.append(Reason("lookalike", f.lookalike_token, W_LOOKALIKE))
    if f.homoglyph_hit:
        reasons.append(Reason("homoglyph_hit", f.homoglyph_token, W_HOMOGLYPH))
    if f.tld_risk >= 1.0:
        reasons.append(Reason("tld_risk", "." + f.tld, W_TLD))
    if f.keyword_count:
        reasons.append(Reason("keyword_count", f.keyword_count, W_KEYWORD))
    if f.hyphen_count > 3 or f.max_label_len > 25:
        reasons.append(Reason("shape", {"hyphens": f.hyphen_count, "max_label_len": f.max_label_len}, W_SHAPE))
    total = sum(r.contribution for r in reasons)
    if total > 1.0:
        reasons.append(Reason("cap", 1.0, 1.0 - total))  # explicit, so reasons always sum to the score
    return reasons


def triage(name: str, issuer: str | None = None, san_count: int = 1) -> TriageResult:
    idx = _brands()
    f = extract(name, issuer, san_count, idx)
    if f.is_public_suffix:  # nobody can register a public suffix; its operator owns the name
        return TriageResult(0.0, False, f.etld1, None, [Reason("public_suffix", f.etld1, 0.0)])
    if f.etld1 in _allow() or f.tld in idx.legit_tlds:  # brand-owned TLDs (.sbi, .jio, .amazon)
        return TriageResult(0.0, False, f.etld1, None, [Reason("allowlisted", f.etld1, 0.0)])
    reasons = score_rules(f)
    score = round(sum(r.contribution for r in reasons), 6)
    return TriageResult(score, score >= SETTINGS.triage_threshold, f.etld1,
                        f.brand.name if f.brand else None, reasons)
