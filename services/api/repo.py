"""Write helpers for the pipeline, workers and seed. Plain SQL against services/api/schema.sql.

Every function takes a Connection and never commits: the caller owns the transaction. Org-owned rows take
their org_id from the transaction's org context (column default current_org(); db.bind_org / set_org_context),
and every multi-row UPDATE also names `org_id = current_org()` so a privileged caller cannot cross tenants.
Shared rows: certificates, and domains with origin_org_id null (the public CT feed).
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
                     source: str, ct_seen_at: datetime | None, received_at: datetime | None = None,
                     private: bool = False) -> tuple[int, bool]:
    """Insert a candidate, or touch last_seen on a repeat (precert + final cert, several logs).
    First-seen timestamps are never overwritten: they are the measured response-time origin.
    private=False: the shared public-feed row. private=True: a row only the current org can see (email)."""
    row = c.execute(sa.text("""
        insert into domains (name, etld1, cert_id, source, ct_seen_at, received_at, candidate_at,
                             triage_score, triage_reasons, brand_matched, origin_org_id)
        values (:name, :etld1, :cert, :source, :ct_seen, :received, clock_timestamp(), :score, cast(:reasons as jsonb),
                :brand, case when :private then current_org() end)
        on conflict (name, origin_org_id) do update set last_seen = now()
        returning id, (xmax = 0) as created"""),
        {"name": name, "etld1": etld1, "cert": cert_id, "source": source, "ct_seen": ct_seen_at, "received": received_at,
         "score": triage.score, "reasons": _j(triage_doc(triage)), "brand": triage.brand, "private": private}).one()
    return row.id, row.created


def set_confirmation(c: sa.Connection, domain_id: int, r: ConfirmResult) -> None:
    """The current org's verdict. A separate row per org: the shared domains row never carries a verdict."""
    status = r.verdict if r.verdict in ("confirmed", "dismissed", "unreachable") else "candidate"
    c.execute(sa.text("""
        insert into domain_verdicts as v (domain_id, status, confirm_reasons, confidence, verdict_at, confirmed_at)
        values (:id, :status, cast(:reasons as jsonb), :conf, clock_timestamp(),
                case when :status = 'confirmed' then clock_timestamp() end)
        on conflict (org_id, domain_id) do update set
          status = excluded.status, confirm_reasons = excluded.confirm_reasons, confidence = excluded.confidence,
          verdict_at = clock_timestamp(),  -- write time, not transaction start: these are measured latencies
          confirmed_at = case when excluded.status = 'confirmed' then coalesce(v.confirmed_at, clock_timestamp())
                              else v.confirmed_at end"""),
        {"status": status, "reasons": _j(r.reasons()), "conf": r.confidence, "id": domain_id})


def save_enrichment(c: sa.Connection, domain_id: int, e: Enrichment) -> None:
    c.execute(sa.text("""
        insert into enrichment (domain_id, ip_addresses, asn, asn_name, country, nameservers, mx_records,
                                cert_issuer, registrar, registered_at, dom_hash, favicon_hash, js_hashes,
                                page_title, partial, errors)
        values (:d, cast(:ips as inet[]), :asn, :asn_name, :cc, :ns, :mx, :issuer, :reg, :reg_at, :dom, :fav, :js,
                :title, :partial, cast(:errors as jsonb))
        on conflict (org_id, domain_id) do update set
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
        on conflict (org_id, kind, value) do update set kind = excluded.kind
        returning id"""), {"k": kind, "v": value}).scalar_one()


def add_edge(c: sa.Connection, domain_id: int, node_id: int, weight: float) -> None:
    created = c.execute(sa.text("""
        insert into graph_edges (domain_id, node_id, weight) values (:d, :n, :w)
        on conflict (domain_id, node_id) do nothing
        returning id"""), {"d": domain_id, "n": node_id, "w": weight}).first()
    if created:
        c.execute(sa.text("update infra_nodes set domain_count = domain_count + 1 where id = :n and org_id = current_org()"),
                  {"n": node_id})


def known_kits(c: sa.Connection) -> dict[str, str]:
    return {r.dom_hash: r.label or r.dom_hash[:12] for r in c.execute(sa.text(
        "select dom_hash, label from known_kits where org_id = current_org()"))}


def add_known_kit(c: sa.Connection, dom_hash: str, label: str | None, source: str) -> None:
    c.execute(sa.text("""insert into known_kits (dom_hash, label, source) values (:h, :l, :s)
                         on conflict (org_id, dom_hash) do nothing"""), {"h": dom_hash, "l": label, "s": source})


def log(c: sa.Connection, channel: str, message: str, severity: int = 0, context: dict | None = None) -> None:
    c.execute(sa.text("insert into ops_log (channel, severity, message, context) values (:c, :s, :m, cast(:x as jsonb))"),
              {"c": channel, "s": severity, "m": message, "x": _j(context) if context is not None else None})


def enqueue_anchor(c: sa.Connection, kind: str, payload: dict) -> int:
    return c.execute(sa.text("insert into anchor_queue (kind, payload) values (:k, cast(:p as jsonb)) returning id"),
                     {"k": kind, "p": _j(payload)}).scalar_one()


# ---------------------------------------------------------------------------------------------------
# Bulk writes. Supabase is ~110 ms per round trip from the demo machine: anything that writes many rows
# sends ONE statement per table, expanding a JSON array server-side with jsonb_to_recordset.
# ---------------------------------------------------------------------------------------------------

def bulk_insert_domains(c: sa.Connection, rows: list[dict]) -> dict[str, int]:
    """rows: name, etld1, source, ct_seen_at, triage_score, triage_reasons, brand_matched, status,
    confirm_reasons, confidence. Inserts PRIVATE rows of the current org (seed) plus that org's verdicts.
    Existing names are left untouched. Returns {name: id} for inserted rows."""
    if not rows:
        return {}
    res = c.execute(sa.text("""
        insert into domains (name, etld1, source, ct_seen_at, candidate_at, triage_score, triage_reasons,
                             brand_matched, origin_org_id)
        select x.name, x.etld1, x.source, x.ct_seen_at, now(), x.triage_score, x.triage_reasons, x.brand_matched,
               current_org()
        from jsonb_to_recordset(cast(:rows as jsonb)) as x(name text, etld1 text, source text,
             ct_seen_at timestamptz, triage_score real, triage_reasons jsonb, brand_matched text)
        on conflict (name, origin_org_id) do nothing
        returning id, name"""), {"rows": _j(rows)})
    ids = {r.name: r.id for r in res}
    verdicts = [{**r, "domain_id": ids[r["name"]]} for r in rows if r["name"] in ids and r.get("status")]
    if verdicts:
        c.execute(sa.text("""
            insert into domain_verdicts (domain_id, status, confirm_reasons, confidence, verdict_at, confirmed_at)
            select x.domain_id, x.status, x.confirm_reasons, x.confidence, now(),
                   case when x.status = 'confirmed' then now() end
            from jsonb_to_recordset(cast(:rows as jsonb)) as x(domain_id bigint, status text, confirm_reasons jsonb,
                 confidence real)"""), {"rows": _j(verdicts)})
    return ids


def bulk_save_enrichment(c: sa.Connection, pairs: list[tuple[int, Enrichment]]) -> None:
    if not pairs:
        return
    rows = [{"domain_id": d, "ip_addresses": e.ip_addresses, "asn": e.asn, "asn_name": e.asn_name, "country": e.country,
             "nameservers": e.nameservers, "mx_records": e.mx_records, "cert_issuer": e.cert_issuer,
             "registrar": e.registrar, "registered_at": e.registered_at, "dom_hash": e.dom_hash,
             "favicon_hash": e.favicon_hash, "js_hashes": e.js_hashes, "page_title": e.page_title,
             "partial": e.partial, "errors": e.errors or None} for d, e in pairs]
    c.execute(sa.text("""
        insert into enrichment (domain_id, ip_addresses, asn, asn_name, country, nameservers, mx_records, cert_issuer,
                                registrar, registered_at, dom_hash, favicon_hash, js_hashes, page_title, partial, errors)
        select x.domain_id, cast(x.ip_addresses as inet[]), x.asn, x.asn_name, x.country, x.nameservers, x.mx_records,
               x.cert_issuer, x.registrar, x.registered_at, x.dom_hash, x.favicon_hash, x.js_hashes, x.page_title,
               x.partial, x.errors
        from jsonb_to_recordset(cast(:rows as jsonb)) as x(domain_id bigint, ip_addresses text[], asn int,
             asn_name text, country text, nameservers text[], mx_records text[], cert_issuer text, registrar text,
             registered_at timestamptz, dom_hash text, favicon_hash text, js_hashes text[], page_title text,
             partial boolean, errors jsonb)
        on conflict (org_id, domain_id) do nothing"""), {"rows": _j(rows)})


def bulk_upsert_nodes(c: sa.Connection, pairs: set[tuple[str, str]]) -> dict[tuple[str, str], int]:
    if not pairs:
        return {}
    res = c.execute(sa.text("""
        insert into infra_nodes (kind, value)
        select x.kind, x.value from jsonb_to_recordset(cast(:rows as jsonb)) as x(kind text, value text)
        on conflict (org_id, kind, value) do update set kind = excluded.kind
        returning id, kind, value"""), {"rows": _j([{"kind": k, "value": v} for k, v in sorted(pairs)])})
    return {(r.kind, r.value): r.id for r in res}


def bulk_add_edges(c: sa.Connection, edges: list[tuple[int, int, float]]) -> None:
    if not edges:
        return
    c.execute(sa.text("""
        insert into graph_edges (domain_id, node_id, weight)
        select x.d, x.n, x.w from jsonb_to_recordset(cast(:rows as jsonb)) as x(d bigint, n bigint, w real)
        on conflict (domain_id, node_id) do nothing"""), {"rows": _j([{"d": d, "n": n, "w": w} for d, n, w in edges])})
    c.execute(sa.text("""
        update infra_nodes i set domain_count = s.n
        from (select node_id, count(*) as n from graph_edges where node_id = any(:ids) and org_id = current_org()
              group by node_id) s
        where i.id = s.node_id and i.org_id = current_org()"""), {"ids": sorted({n for _, n, _ in edges})})
