"""Email signals (spec §3.2). One function per signal; each returns a Signal or None.

strong:   dmarc_fail_brand_from · display_name_brand_spoof · link_domain_confirmed · sender_domain_confirmed
moderate: lookalike_sender_domain · reply_to_mismatch · spf_fail · dkim_fail
weak:     return_path_mismatch · message_id_mismatch · received_anomaly · auth_results_missing
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from services.email.parse import ParsedEmail
from services.enrich.confirm import Signal
from services.ingest.brands import BrandIndex, etld1


@dataclass
class DomainLookup:
    domain_id: int | None
    status: str | None
    campaign_id: str | None
    campaign_label: str | None


Lookup = Callable[[str], DomainLookup]


def _brand_in_display(display: str, idx: BrandIndex):
    """Brand claimed by a display name. Compared with spacing and punctuation removed ("Income Tax
    Department" -> "incometaxdepartment" contains token "incometax"; "H.D.F.C." -> "hdfc"). Tokens of
    <= 3 chars must be a whole word ("vi" inside "service" is not Vodafone Idea)."""
    d = display.lower()
    squashed = re.sub(r"[^a-z0-9]+", "", d)
    words = {w for w in re.split(r"[^a-z0-9]+", d) if w}
    for b in idx.brands:
        if re.sub(r"[^a-z0-9]+", "", b.name.lower()) in squashed:
            return b
        for t in b.tokens:
            if (len(t) > 3 and t in squashed) or t in words:
                return b
    return None


def _hit(look: DomainLookup) -> bool:
    return look.status == "confirmed" or look.campaign_id is not None


def compute_signals(p: ParsedEmail, *, brands: BrandIndex, lookup: Lookup, triage_fn) -> tuple[list[Signal], list[DomainLookup]]:
    out: list[Signal] = []
    linked: list[DomainLookup] = []
    legit = brands.legit_etld1s

    # ---- strong ---------------------------------------------------------------------------------
    if p.auth.get("dmarc") == "fail" and p.from_etld1 in legit:
        out.append(Signal("dmarc_fail_brand_from", "strong",
                          f"DMARC fail for From: {p.from_addr} — a real brand domain sent by someone else"))
    if p.from_display:
        b = _brand_in_display(p.from_display, brands)
        if b and p.from_etld1 and p.from_etld1 not in {etld1(d) for d in b.legit_domains}:
            out.append(Signal("display_name_brand_spoof", "strong",
                              f"display name '{p.from_display}' claims {b.name}; sender domain is {p.from_etld1}"))
    for d in p.link_etld1s:
        look = lookup(d)
        if _hit(look):
            linked.append(look)
            out.append(Signal("link_domain_confirmed", "strong",
                              f"link to {d}: {look.status}" + (f", campaign {look.campaign_label}" if look.campaign_label else "")))
            break
    for d in dict.fromkeys(x for x in (p.from_etld1, p.reply_to_etld1, p.return_path_etld1) if x):
        look = lookup(d)
        if _hit(look):
            linked.append(look)
            out.append(Signal("sender_domain_confirmed", "strong",
                              f"sender domain {d}: {look.status}" + (f", campaign {look.campaign_label}" if look.campaign_label else "")))
            break

    # ---- moderate -------------------------------------------------------------------------------
    for d in dict.fromkeys(x for x in (p.from_etld1, p.reply_to_etld1) if x):
        t = triage_fn(d)
        if t.is_candidate:
            out.append(Signal("lookalike_sender_domain", "moderate",
                              f"{d} triages as a candidate ({t.score:.2f}{', ' + t.brand if t.brand else ''})"))
            break
    if p.reply_to_etld1 and p.from_etld1 and p.reply_to_etld1 != p.from_etld1:
        out.append(Signal("reply_to_mismatch", "moderate", f"Reply-To {p.reply_to_etld1} ≠ From {p.from_etld1}"))
    if p.auth.get("spf") in ("fail", "softfail"):
        out.append(Signal("spf_fail", "moderate", f"SPF {p.auth['spf']}"))
    if p.auth.get("dkim") == "fail":
        out.append(Signal("dkim_fail", "moderate", "DKIM fail"))

    # ---- weak -----------------------------------------------------------------------------------
    if p.return_path_etld1 and p.from_etld1 and p.return_path_etld1 != p.from_etld1 and p.auth.get("dmarc") != "pass":
        # an aligned DMARC pass explains a third-party ESP Return-Path; without it the mismatch is a weak signal
        out.append(Signal("return_path_mismatch", "weak", f"Return-Path {p.return_path_etld1} ≠ From {p.from_etld1}"))
    if p.message_id_domain and p.from_etld1 and p.message_id_domain != p.from_etld1 and p.auth.get("dmarc") != "pass":
        out.append(Signal("message_id_mismatch", "weak", f"Message-ID domain {p.message_id_domain} ≠ From {p.from_etld1}"))
    times = [h["at"] for h in p.received if h.get("at")]
    if any(datetime.fromisoformat(b) < datetime.fromisoformat(a) for a, b in zip(times, times[1:])):
        out.append(Signal("received_anomaly", "weak", "Received hop timestamps go backwards"))
    if "Authentication-Results" in p.absent and p.from_addr:
        out.append(Signal("auth_results_missing", "weak", "no Authentication-Results header"))
    return out, linked
