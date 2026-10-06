"""Email verdict gate (spec §3.3) and correlation into the domain pipeline (§3.4).

malicious  <=>  >= 2 STRONG signals (also enforced by a database check).
suspicious <=>  any signal, < 2 strong — rendered grey, worded "Suspicious — not verified".
clean      <=>  no signals.
Email NEVER confirms a domain: link and sender domains that triage as candidates enter the normal
CT-confirmation queue with source='email'.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Literal

import sqlalchemy as sa

from services.api import repo
from services.email.parse import ParsedEmail, parse_email
from services.email.signals import DomainLookup, Lookup, compute_signals
from services.enrich.confirm import Signal
from services.ingest.brands import BrandIndex
from services.ingest.triage import triage

__all__ = ["DomainLookup", "EmailVerdict", "analyze", "db_lookup", "persist_and_correlate"]


@dataclass
class EmailVerdict:
    verdict: Literal["malicious", "suspicious", "clean"]
    signals: list[Signal]
    strong_count: int
    parsed: ParsedEmail
    linked_campaign_ids: list[str] = field(default_factory=list)
    linked_domain_ids: list[int] = field(default_factory=list)
    linked_campaigns: list[dict] = field(default_factory=list)


def analyze(raw: str | bytes, *, brands: BrandIndex, lookup: Lookup, triage_fn=triage) -> EmailVerdict:
    p = parse_email(raw)
    signals, linked = compute_signals(p, brands=brands, lookup=lookup, triage_fn=triage_fn)
    strong = sum(s.strength == "strong" for s in signals)
    verdict = "malicious" if strong >= 2 else ("suspicious" if signals else "clean")
    camps = {x.campaign_id: x.campaign_label for x in linked if x.campaign_id}
    return EmailVerdict(verdict, signals, strong, p, list(camps),
                        sorted({x.domain_id for x in linked if x.domain_id is not None}),
                        [{"id": k, "label": v} for k, v in camps.items()])


def db_lookup(c: sa.Connection) -> Lookup:
    cache: dict[str, DomainLookup] = {}

    def look(etld1: str) -> DomainLookup:
        if etld1 not in cache:
            r = c.execute(sa.text("""
                select d.id, d.status, d.campaign_id::text as cid, cp.label from domains d
                left join campaigns cp on cp.id = d.campaign_id
                where d.etld1 = :e or d.name = :e
                order by (d.status = 'confirmed') desc, d.campaign_id is null limit 1"""), {"e": etld1}).first()
            cache[etld1] = DomainLookup(r.id, r.status, r.cid, r.label) if r else DomainLookup(None, None, None, None)
        return cache[etld1]
    return look


def persist_and_correlate(c: sa.Connection, v: EmailVerdict, source: Literal["analyst", "sample"]
                          ) -> tuple[str, list[int]]:
    """Insert the analysis; triage every sender and link domain and add candidates (source='email').
    Returns (analysis id, newly created candidate domain ids) — the caller queues them for confirmation."""
    p = v.parsed
    new_ids: list[int] = []
    for d in dict.fromkeys(x for x in (p.from_etld1, p.reply_to_etld1, *p.link_etld1s) if x):
        t = triage(d)
        if t.is_candidate:
            did, created = repo.upsert_candidate(c, name=d, etld1=t.etld1, cert_id=None, triage=t, source="email",
                                                 ct_seen_at=None)
            if created:
                new_ids.append(did)
    aid = str(uuid.uuid4())
    c.execute(sa.text("""
        insert into email_analyses (id, source, from_addr, from_etld1, reply_to_etld1, return_path_etld1, auth_results,
               received_hops, urls, signals, strong_count, verdict, linked_campaign_ids, linked_domain_ids)
        values (:id, :src, :fa, :fe, :re, :rp, cast(:auth as jsonb), cast(:hops as jsonb), :urls, cast(:sig as jsonb),
                :sc, :v, cast(:lc as uuid[]), :ld)"""),
        {"id": aid, "src": source, "fa": p.from_addr, "fe": p.from_etld1, "re": p.reply_to_etld1,
         "rp": p.return_path_etld1, "auth": json.dumps(p.auth), "hops": json.dumps(p.received), "urls": p.urls,
         "sig": json.dumps([s.__dict__ for s in v.signals]), "sc": v.strong_count, "v": v.verdict,
         "lc": v.linked_campaign_ids, "ld": v.linked_domain_ids})
    repo.log(c, "email", f"email {aid[:8]}: {v.verdict} ({v.strong_count} strong) from {p.from_etld1 or 'unknown'}"
             + (f"; {len(new_ids)} new candidates" if new_ids else ""), context={"analysis_id": aid})
    return aid, new_ids
