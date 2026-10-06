"""After a verdict: persist status, enrichment, graph edges, known kit, campaign, evidence bundle,
unsent abuse report, and an evidence-anchor queue entry — in the caller's single transaction.
Shared by the live enrich worker and the labelled seed.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa

from evidence.bundle import build_bundle
from evidence.report import render_abuse_report
from services.api import repo
from services.enrich.confirm import ConfirmResult
from services.enrich.enrichers import Enrichment
from services.enrich.fetch import FetchedPage
from services.graph.build import edges_for, recluster

TOOL_VERSIONS = {"qcertchain": "0.1.0", "collector": "services.api.pipeline"}


def _dump(v) -> bytes:
    return json.dumps(v, indent=1, default=str, ensure_ascii=False).encode("utf-8")


def evidence_artifacts(page: FetchedPage | None, e: Enrichment, *, source: str) -> tuple[dict[str, bytes], bool]:
    """BLOCKCHAIN.md §5 artifact set. Returns (artifacts, partial)."""
    arts: dict[str, bytes] = {}
    if page is not None:
        arts["dom.html"] = page.html.encode("utf-8")
        arts["headers.json"] = _dump({"status": page.status, "final_url": page.final_url,
                                      "redirect_chain": page.redirect_chain, "headers": page.headers, "via": page.via})
        if page.screenshot:
            arts["screenshot.png"] = page.screenshot
    if e.cert_pem:
        arts["cert.pem"] = e.cert_pem.encode("ascii")
    arts["whois.json"] = _dump(e.raw.get("rdap") or {"registrar": e.registrar, "registered_at": e.registered_at,
                                                     "abuse_email": e.abuse_email})
    arts["dns.json"] = _dump(e.raw.get("dns") or {"A": e.ip_addresses, "NS": e.nameservers, "MX": e.mx_records})
    arts["asn.json"] = _dump(e.raw.get("asn") or {"asn": e.asn, "asn_name": e.asn_name, "country": e.country})
    arts["kit.json"] = _dump({"dom_hash": e.dom_hash, "favicon_hash": e.favicon_hash, "js_hashes": e.js_hashes})
    arts["meta.json"] = _dump({"collected_at": datetime.now(timezone.utc), "source": source,
                               "tool_versions": TOOL_VERSIONS, "enrichment_errors": e.errors})
    partial = page is None or not page.screenshot or "cert.pem" not in arts or e.partial
    return arts, partial


@dataclass
class PreparedBundle:
    bundle_id: str
    domain_id: int
    campaign_id: str | None
    bundle: object                 # evidence.bundle.Bundle
    partial: bool
    report: str
    recipient: str | None


def prepare_bundle(domain_id: int, name: str, result: ConfirmResult, page: FetchedPage | None, e: Enrichment, *,
                   campaign_id: str | None, campaign_label: str | None, evidence_dir: Path | str,
                   signing_key_hex: str, source: str) -> PreparedBundle:
    """Write artifacts, build the Merkle root, sign it, render the (unsent) report. No database access."""
    bundle_id = str(uuid.uuid4())
    arts, partial = evidence_artifacts(page, e, source=source)
    b = build_bundle(Path(evidence_dir), bundle_id, arts, signing_key_hex, partial=partial)
    body = render_abuse_report(domain=name, recipient=e.abuse_email, bundle=b,
                               signals=[s.__dict__ for s in result.signals],
                               enrichment={"ip_addresses": e.ip_addresses, "asn": e.asn, "asn_name": e.asn_name,
                                           "nameservers": e.nameservers, "registrar": e.registrar,
                                           "registered_at": e.registered_at, "cert_issuer": e.cert_issuer},
                               campaign_label=campaign_label, generated_at=datetime.now(timezone.utc))
    return PreparedBundle(bundle_id, domain_id, campaign_id, b, partial, body, e.abuse_email)


def insert_bundles(c: sa.Connection, prepared: list[PreparedBundle]) -> None:
    """Four statements for any number of bundles: bundles, artifacts, reports (sent=false), anchor queue."""
    if not prepared:
        return
    j = lambda v: json.dumps(v, default=str)  # noqa: E731
    c.execute(sa.text("""
        insert into evidence_bundles (id, domain_id, campaign_id, bundle_root, signature, collector_pk, artifact_dir, partial)
        select x.id, x.domain_id, x.campaign_id, x.root, x.sig, x.pk, x.dir, x.partial
        from jsonb_to_recordset(cast(:rows as jsonb)) as x(id uuid, domain_id bigint, campaign_id uuid, root text,
             sig text, pk text, dir text, partial boolean)"""),
        {"rows": j([{"id": p.bundle_id, "domain_id": p.domain_id, "campaign_id": p.campaign_id, "root": p.bundle.root,
                     "sig": p.bundle.signature, "pk": p.bundle.collector_pk, "dir": p.bundle.dir,
                     "partial": p.partial} for p in prepared])})
    c.execute(sa.text("""
        insert into evidence_artifacts (bundle_id, name, sha256, size_bytes)
        select x.b, x.name, x.sha, x.size from jsonb_to_recordset(cast(:rows as jsonb)) as x(b uuid, name text, sha text, size int)"""),
        {"rows": j([{"b": p.bundle_id, "name": a.name, "sha": a.sha256, "size": a.size_bytes}
                    for p in prepared for a in p.bundle.artifacts])})
    c.execute(sa.text("""
        insert into abuse_reports (bundle_id, recipient, body)
        select x.b, x.r, x.body from jsonb_to_recordset(cast(:rows as jsonb)) as x(b uuid, r text, body text)"""),
        {"rows": j([{"b": p.bundle_id, "r": p.recipient, "body": p.report} for p in prepared])})
    c.execute(sa.text("""
        insert into anchor_queue (kind, payload)
        select 'evidence', x.p from jsonb_to_recordset(cast(:rows as jsonb)) as x(p jsonb)"""),
        {"rows": j([{"p": {"bundle_id": p.bundle_id, "bundle_root": p.bundle.root, "campaign_id": p.campaign_id}}
                    for p in prepared])})


def make_bundle(c: sa.Connection, domain_id: int, name: str, result: ConfirmResult, page: FetchedPage | None,
                e: Enrichment, *, evidence_dir: Path | str, signing_key_hex: str, source: str) -> str:
    camp = c.execute(sa.text("select d.campaign_id, c.label from domains d left join campaigns c on c.id = d.campaign_id "
                             "where d.id = :d"), {"d": domain_id}).one()
    p = prepare_bundle(domain_id, name, result, page, e,
                       campaign_id=str(camp.campaign_id) if camp.campaign_id else None, campaign_label=camp.label,
                       evidence_dir=evidence_dir, signing_key_hex=signing_key_hex, source=source)
    insert_bundles(c, [p])
    return p.bundle_id


def persist_result(c: sa.Connection, domain_id: int, name: str, result: ConfirmResult, page: FetchedPage | None,
                   e: Enrichment, *, evidence_dir: Path | str, signing_key_hex: str, source: str = "certstream",
                   do_recluster: bool = True) -> str | None:
    """Returns the evidence bundle id for a confirmed domain, else None."""
    repo.set_confirmation(c, domain_id, result)
    repo.save_enrichment(c, domain_id, e)
    if result.verdict != "confirmed":
        repo.log(c, "confirm", f"{name}: {result.verdict} ({result.strong_count} strong)",
                 context={"domain_id": domain_id})
        return None
    for kind, value, weight in edges_for(e):
        repo.add_edge(c, domain_id, repo.upsert_node(c, kind, value), weight)
    if e.dom_hash:
        repo.add_known_kit(c, e.dom_hash, None, "confirmed")
    if do_recluster:
        recluster(c)
    bundle_id = make_bundle(c, domain_id, name, result, page, e, evidence_dir=evidence_dir,
                            signing_key_hex=signing_key_hex, source=source)
    repo.log(c, "confirm", f"{name}: confirmed ({result.strong_count} strong) · bundle {bundle_id[:8]}",
             context={"domain_id": domain_id, "bundle_id": bundle_id})
    return bundle_id
