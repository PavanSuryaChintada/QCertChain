"""The 12 triage features (MODELS.md §2). ONE implementation, shared by runtime triage and training.

No domain-age feature: it needs WHOIS (200-2000 ms) and breaks the 5 ms budget.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from rapidfuzz import process
from rapidfuzz.distance import DamerauLevenshtein

from services.ingest.brands import _EXTRACT, Brand, BrandIndex
from services.ingest.homoglyph import skeleton

KEYWORDS = ("verify", "kyc", "secure", "login", "update", "netbanking", "account")
RISKY_TLDS = frozenset({"top", "xyz", "click", "cf", "tk", "gq", "buzz", "rest"})
FREE_CAS = ("let's encrypt", "zerossl")
_SEG = re.compile(r"[.\-_]+")  # digits stay inside segments: hex like "vi0svszw" must not yield "vi"
SHORT_TOKEN = 3  # tokens this long or shorter match only a whole segment
LOOKALIKE_MIN = 5  # edit distance is only used for tokens at least this long

FEATURE_ORDER = ("brand_token_exact", "min_edit_distance", "homoglyph_hit", "tld_risk", "keyword_count",
                 "hyphen_count", "max_label_len", "digit_ratio", "subdomain_depth", "entropy",
                 "issuer_is_free_ca", "san_count")


def lookalike_limit(token_len: int) -> int:
    """Max Damerau-Levenshtein distance that still counts as a lookalike of a token this long."""
    return 1 if token_len < 8 else 2


@dataclass
class Features:
    brand_token_exact: bool
    min_edit_distance: int          # 99 = no comparable token
    homoglyph_hit: bool
    tld_risk: float                 # rules: 1.0 risky / 0.0; model: empirical rate
    keyword_count: int
    hyphen_count: int
    max_label_len: int
    digit_ratio: float
    subdomain_depth: int
    entropy: float
    issuer_is_free_ca: bool
    san_count: int
    # context, not model inputs
    name: str = ""
    etld1: str = ""
    tld: str = ""
    brand: Brand | None = None
    matched_token: str | None = None
    lookalike_token: str | None = None
    homoglyph_token: str | None = None
    keywords: list[str] = field(default_factory=list)
    is_public_suffix: bool = False
    # A segment whose confusable skeleton IS a brand token while the segment itself is not (owner decision 3):
    # a near-certain lookalike, scored on its own. Not a model input (the trained model was rejected).
    skeleton_exact_token: str | None = None

    def vector(self) -> list[float]:
        return [float(getattr(self, f)) for f in FEATURE_ORDER]


def _decode(name: str) -> str:
    if "xn--" not in name:
        return name
    out = []
    for label in name.split("."):
        try:
            out.append(label.encode("ascii").decode("idna") if label.startswith("xn--") else label)
        except (UnicodeError, ValueError):
            out.append(label)
    return ".".join(out)


def _segments(text: str) -> set[str]:
    """Delimited segments, plus each with edge digits stripped ("sbi1" -> "sbi", "2sbi" -> "sbi")."""
    out = set()
    for s in _SEG.split(text):
        if s:
            out.add(s)
            out.add(s.strip("0123456789"))
    out.discard("")
    return out


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values())


def _alternation(words) -> re.Pattern:
    # longest first so the leftmost match is also the most specific token
    return re.compile("|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True)))


class _Prepared:
    """Per-BrandIndex precomputation. Everything in the hot path is a C-level call:
    compiled alternations for substring tokens, set intersection for short tokens,
    rapidfuzz.process for edit distance over a per-length candidate list."""

    def __init__(self, idx: BrandIndex):
        self.idx = idx
        self.tokens = list(idx.by_token)
        self.short = frozenset(t for t in self.tokens if len(t) <= SHORT_TOKEN)
        self.long_re = _alternation(t for t in self.tokens if len(t) > SHORT_TOKEN)
        self.skel_of = {}  # canonical form -> token
        for t in self.tokens:
            self.skel_of.setdefault(skeleton(t), t)
        self.skel_short = {k: v for k, v in self.skel_of.items() if len(v) <= SHORT_TOKEN}
        self.skel_long_re = _alternation(k for k, v in self.skel_of.items() if len(v) > SHORT_TOKEN)
        long_tokens = [t for t in self.tokens if len(t) >= LOOKALIKE_MIN]
        # for a segment of length L: every long token within +-2 characters
        self.near: dict[int, list[str]] = {
            L: [t for t in long_tokens if abs(len(t) - L) <= 2] for L in range(1, 64)}

    def exact(self, body: str, segs: set[str]) -> str | None:
        m = self.long_re.search(body)
        if m:
            return m.group(0)
        hit = self.short & segs
        return min(hit) if hit else None


_PREP: dict[int, _Prepared] = {}


def _prep(idx: BrandIndex) -> _Prepared:
    p = _PREP.get(id(idx))
    if p is None:
        p = _PREP[id(idx)] = _Prepared(idx)
    return p


def extract(name: str, issuer: str | None, san_count: int, idx: BrandIndex,
            tld_rates: dict[str, float] | None = None) -> Features:
    p = _prep(idx)
    name = _decode(name.strip().lower().rstrip("."))
    parts = _EXTRACT(name)
    # A TLD missing from the PSL snapshot (a new gTLD) yields suffix "": treat its last label as
    # the suffix so the name is still scored. Only a name that IS a known suffix is unregistrable.
    is_suffix = bool(parts.suffix) and parts.suffix == name
    suffix = parts.suffix or name.rsplit(".", 1)[-1]
    body = name[: -len(suffix) - 1] if suffix and name.endswith("." + suffix) else name
    tld = suffix.rsplit(".", 1)[-1] if suffix else ""
    reg = parts.registered_domain or (".".join(name.split(".")[-2:]) if not parts.suffix else name)
    segs = [s for s in _SEG.split(body) if s]
    seg_set = _segments(body)

    matched = p.exact(body, seg_set)

    best_d, best_t = 99, None
    for s in segs:
        # A segment that already contains an exact token is evidence for that token only:
        # counting it again as a lookalike double-counts one observation.
        cands = p.near.get(len(s))
        if not cands or len(s) < LOOKALIKE_MIN - 1 or p.long_re.search(s):
            continue
        for t, d, _ in process.extract(s, cands, scorer=DamerauLevenshtein.distance,
                                       score_cutoff=2, limit=None):
            # A segment shorter than the token may differ by one edit only: "onlines" is
            # a common word two deletions from "onlinesbi", not a lookalike of it.
            limit = lookalike_limit(len(t)) if len(s) >= len(t) else 1
            if 0 < d <= limit and d < best_d:
                best_d, best_t = d, t
    lookalike = best_t

    # Exact skeleton match, checked BEFORE edit distance and the substring homoglyph scan: a whole segment whose
    # skeleton equals a brand token, while the segment is not literally that token. Non-ASCII confusables count at
    # any length; ASCII-only confusions (l/1/0) only for tokens of LOOKALIKE_MIN+ chars ("vl" -> "vi" is noise).
    skel_exact = None
    sk = skeleton(body)
    if sk != body and matched is None:
        raw_segs = [s for s in _SEG.split(body) if s]
        for raw in raw_segs:
            t = p.skel_of.get(skeleton(raw))
            if t and raw != t and (not raw.isascii() or len(t) >= LOOKALIKE_MIN):
                skel_exact = t
                break
    if skel_exact is not None:  # one observation, counted once: no lookalike / substring homoglyph on top
        lookalike = None
        best_d = 99

    homo_token = None
    if sk != body and skel_exact is None:
        for m in p.skel_long_re.finditer(sk):
            t = p.skel_of[m.group(0)]
            if t not in body:
                homo_token = t
                break
        # ASCII-only confusion (l/1/i, 0/o) on a 2-3 letter token is noise: "vl" -> "vi".
        if homo_token is None and not body.isascii():
            for seg in _segments(sk):
                t = p.skel_short.get(seg)
                if t and t not in seg_set:
                    homo_token = t
                    break

    kws = [k for k in KEYWORDS if k in body]
    labels = name.split(".")
    reg_label = reg[: -len(suffix) - 1] if suffix and reg.endswith("." + suffix) else reg
    brand_tok = matched or skel_exact or lookalike or homo_token
    return Features(
        brand_token_exact=matched is not None,
        min_edit_distance=0 if matched else best_d,
        homoglyph_hit=homo_token is not None,
        tld_risk=(tld_rates.get(tld, 0.0) if tld_rates is not None else float(tld in RISKY_TLDS)),
        keyword_count=len(kws),
        hyphen_count=name.count("-"),
        max_label_len=max((len(x) for x in labels), default=0),
        digit_ratio=sum(c.isdigit() for c in name) / max(len(name), 1),
        subdomain_depth=max(len(labels) - len(suffix.split(".")) if suffix else len(labels) - 1, 0),
        entropy=_entropy(reg_label),
        issuer_is_free_ca=bool(issuer) and issuer.lower().startswith(FREE_CAS),
        san_count=san_count,
        name=name, etld1=reg, tld=tld,
        brand=idx.by_token[brand_tok] if brand_tok else None,
        matched_token=matched, lookalike_token=lookalike, homoglyph_token=homo_token, keywords=kws,
        is_public_suffix=is_suffix, skeleton_exact_token=skel_exact,
    )
