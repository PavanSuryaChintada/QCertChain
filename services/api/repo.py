"""Repository layer. Plain SQL against services/api/schema.sql (the source of truth).

Every function takes a Connection and never commits: the caller owns the transaction.
"""
from __future__ import annotations

import json
from datetime import datetime

import sqlalchemy as sa

from services.enrich.confirm import ConfirmResult
from services.enrich.enrichers import Enrichment
from services.ingest.certparse import CertRecord
from services.ingest.triage import TriageResult


def _j(v) -> str:
    return json.dumps(v, default=str)


def upsert_cert(c: sa.Connection, rec: CertRecord) -> int:
    return c.execute(sa.text("""
        insert into certificates (ct_seen_at, not_before, not_after, issuer, serial, fingerprint, san_count, source)
        values (:seen, :nb, :na, :issuer, :serial, :fp, :sans, :source)
        on conflict (fingerprint) do update set fingerprint = excluded.fingerprint
        returning id"""), {"seen": rec.seen_at, "nb": rec.not_before, "na": rec.not_after, "issuer": rec.issuer,
                           "serial": rec.serial, "fp": rec.fingerprint or None, "sans": min(rec.san_count, 32767),
                           "source": rec.source}).scalar_one()


def triage_doc(t: TriageResult) -> dict:
    return {"score": t.score, "provenance": t.provenance, "threshold": t.threshold,
            "reasons": [{"feature": r.feature, "value": r.value, "contribution": r.contribution} for r in t.reasons]}


def upsert_candidate(c: sa.Connection, *, name: str, etld1: str, cert_id: int | None, triage: TriageResult,
                     source: str, ct_seen_at: datetime | None) -> tuple[int, bool]:
    """Insert a candidate, or touch last_seen on a repeat (precert + final cert, several logs).
    First-seen timestamps are never overwritten: they are the measured response-time origin."""
    row = c.execute(sa.text("""
        insert into domains (name, etld1, cert_id, source, ct_seen_at, candidate_at,
                             triage_score, triage_reasons, brand_matched)
        values (:name, :etld1, :cert, :source, :ct_seen, now(), :score, cast(:reasons as jsonb), :brand)
        on conflict (name) do update set last_seen = now()
        returning id, (xmax = 0) as created"""),
        {"name": name, "etld1": etld1, "cert": cert_id, "source": source, "ct_seen": ct_seen_at,
         "score": triage.score, "reasons": _j(triage_doc(triage)), "brand": triage.brand}).one()
    return row.id, row.created


def set_confirmation(c: sa.Connection, domain_id: int, r: ConfirmResult) -> None:
    status = r.verdict if r.verdict in ("confirmed", "dismissed", "unreachable") else "candidate"
    c.execute(sa.text("""
        update domains set status = :status, confirm_reasons = cast(:reasons as jsonb), confidence = :conf,
               confirmed_at = case when :status = 'confirmed' then coalesce(confirmed_at, now()) else confirmed_at end
        where id = :id"""), {"status": status, "reasons": _j(r.reasons()), "conf": r.confidence, "id": domain_id})


def save_enrichment(c: sa.Connection, domain_id: int, e: Enrichment) -> None:
    c.execute(sa.text("""
        insert into enrichment (domain_id, ip_addresses, asn, asn_name, country, nameservers, mx_records,
                                cert_issuer, registrar, registered_at, dom_hash, favicon_hash, js_hashes,
                                page_title, partial, errors)
        values (:d, cast(:ips as inet[]), :asn, :asn_name, :cc, :ns, :mx, :issuer, :reg, :reg_at, :dom, :fav, :js,
                :title, :partial, cast(:errors as jsonb))
        on conflict (domain_id) do update set
          ip_addresses = excluded.ip_addresses, asn = excluded.asn, asn_name = excluded.asn_name,
          country = excluded.country, nameservers = excluded.nameservers, mx_records = excluded.mx_records,
          cert_issuer = excluded.cert_issuer, registrar = excluded.registrar, registered_at = excluded.registered_at,
          dom_hash = excluded.dom_hash, favicon_hash = excluded.favicon_hash, js_hashes = excluded.js_hashes,
          page_title = excluded.page_title, partial = excluded.partial, errors = excluded.errors,
          enriched_at = now()"""),
        {"d": domain_id, "ips": e.ip_addresses, "asn": e.asn, "asn_name": e.asn_name, "cc": e.country,
         "ns": e.nameservers, "mx": e.mx_records, "issuer": e.cert_issuer, "reg": e.registrar,
         "reg_at": e.registered_at, "dom": e.dom_hash, "fav": e.favicon_hash, "js": e.js_hashes,
         "title": e.page_title, "partial": e.partial, "errors": _j(e.errors or None)})


def upsert_node(c: sa.Connection, kind: str, value: str) -> int:
    return c.execute(sa.text("""
        insert into infra_nodes (kind, value) values (:k, :v)
        on conflict (kind, value) do update set kind = excluded.kind
        returning id"""), {"k": kind, "v": value}).scalar_one()


def add_edge(c: sa.Connection, domain_id: int, node_id: int, weight: float) -> None:
    created = c.execute(sa.text("""
        insert into graph_edges (domain_id, node_id, weight) values (:d, :n, :w)
        on conflict (domain_id, node_id) do nothing
        returning id"""), {"d": domain_id, "n": node_id, "w": weight}).first()
    if created:
        c.execute(sa.text("update infra_nodes set domain_count = domain_count + 1 where id = :n"), {"n": node_id})


def known_kits(c: sa.Connection) -> dict[str, str]:
    return {r.dom_hash: r.label or r.dom_hash[:12] for r in c.execute(sa.text("select dom_hash, label from known_kits"))}


def add_known_kit(c: sa.Connection, dom_hash: str, label: str | None, source: str) -> None:
    c.execute(sa.text("""insert into known_kits (dom_hash, label, source) values (:h, :l, :s)
                         on conflict (dom_hash) do nothing"""), {"h": dom_hash, "l": label, "s": source})


def log(c: sa.Connection, channel: str, message: str, severity: int = 0, context: dict | None = None) -> None:
    c.execute(sa.text("insert into ops_log (channel, severity, message, context) values (:c, :s, :m, cast(:x as jsonb))"),
              {"c": channel, "s": severity, "m": message, "x": _j(context) if context is not None else None})


def enqueue_anchor(c: sa.Connection, kind: str, payload: dict) -> int:
    return c.execute(sa.text("insert into anchor_queue (kind, payload) values (:k, cast(:p as jsonb)) returning id"),
                     {"k": kind, "p": _j(payload)}).scalar_one()
