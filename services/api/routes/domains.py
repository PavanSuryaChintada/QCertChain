"""Candidates and domain detail. Every verdict is returned with its reasons — a verdict without reasons is a bug."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from services.api import cursor
from services.api.deps import Scope, get_redis, get_scope
from services.api.repos import domains as repo_domains
from services.api.models import (CandidateCounts, CandidateItem, ConfirmationOut, DomainDetail, DomainStatus, EnrichmentOut, Page,
                                 SignalOut, TriageOut)
from services.config import SETTINGS

router = APIRouter()


@router.get("/candidates", response_model=Page[CandidateItem])
def candidates(status: DomainStatus | None = None, min_score: float | None = Query(None, ge=0, le=1),
               limit: int = cursor.LimitQ, cursor_: str | None = Query(None, alias="cursor", max_length=512), s: Scope = Depends(get_scope)):
    rows = repo_domains.list_candidates(s, status=status, min_score=min_score, limit=limit,
                                        after=cursor.decode(cursor_, 2))
    return cursor.page(rows, limit, lambda r: [r["first_seen"], r["id"]])


@router.get("/candidates/counts", response_model=CandidateCounts)
def candidate_counts(s: Scope = Depends(get_scope)):
    """Counts per status for the segmented filter (one statement), instead of a total on every page."""
    return repo_domains.counts(s)


@router.get("/domains/{domain_id}", response_model=DomainDetail)
def domain_detail(domain_id: int, s: Scope = Depends(get_scope)):
    r = repo_domains.detail(s, domain_id)
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
async def force_confirm(domain_id: int, s: Scope = Depends(get_scope), r=Depends(get_redis)):
    if not repo_domains.exists(s, domain_id):
        raise HTTPException(404, f"domain {domain_id} not found")
    await r.lpush("enrich:queue", f"force:{s.org_id}:{domain_id}")  # confirmed on behalf of THIS org
    return {"queued": True, "domain_id": domain_id}
