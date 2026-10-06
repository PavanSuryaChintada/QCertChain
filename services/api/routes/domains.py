"""Candidates and domain detail. Every verdict is returned with its reasons — a verdict without reasons is a bug."""
from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query

from services.api.deps import get_conn, get_redis
from services.api.models import (CandidateItem, ConfirmationOut, DomainDetail, DomainStatus, EnrichmentOut, Page,
                                 SignalOut, TriageOut)
from services.config import SETTINGS

router = APIRouter()


@router.get("/candidates", response_model=Page[CandidateItem])
def candidates(status: DomainStatus | None = None, min_score: float | None = Query(None, ge=0, le=1),
               limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), c=Depends(get_conn)):
    rows = c.execute(sa.text("""
        select id, name, etld1, status, triage_score, brand_matched, confidence, campaign_id::text, first_seen, source,
               count(*) over () as total
        from domains
        where (cast(:status as text) is null or status = :status)
          and (cast(:min_score as real) is null or triage_score >= :min_score)
        order by first_seen desc, id desc limit :limit offset :offset"""),
        {"status": status, "min_score": min_score, "limit": limit, "offset": offset}).mappings().all()
    total = rows[0]["total"] if rows else 0
    return {"items": [{k: v for k, v in r.items() if k != "total"} for r in rows], "total": total,
            "limit": limit, "offset": offset}


@router.get("/domains/{domain_id}", response_model=DomainDetail)
def domain_detail(domain_id: int, c=Depends(get_conn)):
    r = c.execute(sa.text("""
        select d.*, d.campaign_id::text as campaign_id_s, e.domain_id as has_enrichment,
               e.ip_addresses::text[] as ips, e.asn, e.asn_name, e.country, e.nameservers, e.cert_issuer, e.registrar,
               e.registered_at, e.dom_hash, e.favicon_hash, e.partial, e.errors,
               b.id::text as bundle_id,
               exists(select 1 from evidence_artifacts a where a.bundle_id = b.id and a.name = 'screenshot.png') as shot
        from domains d
        left join enrichment e on e.domain_id = d.id
        left join lateral (select id from evidence_bundles where domain_id = d.id order by created_at desc limit 1) b on true
        where d.id = :id"""), {"id": domain_id}).mappings().one_or_none()
    if r is None:
        raise HTTPException(404, f"domain {domain_id} not found")
    tr = r["triage_reasons"] or {}
    triage = TriageOut(score=r["triage_score"], provenance=tr.get("provenance", "rules"),
                       threshold=tr.get("threshold", SETTINGS.triage_threshold), reasons=tr.get("reasons", []))
    confirmation = None
    cr = r["confirm_reasons"]
    if cr:
        confirmation = ConfirmationOut(
            verdict=cr.get("verdict", r["status"]), confidence=r["confidence"], confirmed_at=r["confirmed_at"],
            signals=[SignalOut(**s) for s in cr.get("signals", [])], strong_count=cr.get("strong_count", 0),
            screenshot_url=f"/evidence/{r['bundle_id']}/artifacts/screenshot.png" if r["shot"] else None)
    enrichment = None
    if r["has_enrichment"] is not None:
        enrichment = EnrichmentOut(ip_addresses=r["ips"] or [], asn=r["asn"], asn_name=r["asn_name"],
                                   country=r["country"], nameservers=r["nameservers"] or [],
                                   cert_issuer=r["cert_issuer"], registrar=r["registrar"],
                                   registered_at=r["registered_at"], dom_hash=r["dom_hash"],
                                   favicon_hash=r["favicon_hash"], partial=bool(r["partial"]), errors=r["errors"])
    return DomainDetail(id=r["id"], name=r["name"], etld1=r["etld1"], status=r["status"], source=r["source"],
                        first_seen=r["first_seen"], last_seen=r["last_seen"], triage=triage,
                        confirmation=confirmation, enrichment=enrichment, campaign_id=r["campaign_id_s"],
                        evidence_bundle_id=r["bundle_id"])


@router.post("/domains/{domain_id}/confirm", status_code=202)
async def force_confirm(domain_id: int, c=Depends(get_conn), r=Depends(get_redis)):
    if c.execute(sa.text("select 1 from domains where id = :d"), {"d": domain_id}).first() is None:
        raise HTTPException(404, f"domain {domain_id} not found")
    await r.lpush("enrich:queue", f"force:{domain_id}")
    return {"queued": True, "domain_id": domain_id}
