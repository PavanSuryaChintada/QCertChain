from __future__ import annotations

import sqlalchemy as sa

from services.api.deps import Scope


def list_candidates(s: Scope, *, status: str | None, min_score: float | None, limit: int, offset: int) -> list[dict]:
    """Shared public-feed candidates plus this org's private ones, each with THIS org's verdict only."""
    return [dict(r) for r in s.conn.execute(sa.text("""
        select id, name, etld1, status, triage_score, brand_matched, confidence, campaign_id::text, first_seen, source,
               count(*) over () as total
        from org_domains
        where (cast(:status as text) is null or status = :status)
          and (cast(:min_score as real) is null or triage_score >= :min_score)
        order by first_seen desc, id desc limit :limit offset :offset"""),
        {"status": status, "min_score": min_score, "limit": limit, "offset": offset}).mappings()]


def detail(s: Scope, domain_id: int) -> dict | None:
    r = s.conn.execute(sa.text("""
        select d.*, d.campaign_id::text as campaign_id_s, e.domain_id as has_enrichment,
               array(select host(x) from unnest(e.ip_addresses) x) as ips, e.asn, e.asn_name, e.country,
               e.nameservers, e.cert_issuer, e.registrar, e.registered_at, e.dom_hash, e.favicon_hash, e.partial,
               e.errors, b.id::text as bundle_id,
               exists(select 1 from evidence_artifacts a where a.bundle_id = b.id and a.name = 'screenshot.png') as shot
        from org_domains d
        left join enrichment e on e.domain_id = d.id and e.org_id = :org
        left join lateral (select id from evidence_bundles where domain_id = d.id and org_id = :org
                           order by created_at desc limit 1) b on true
        where d.id = :id"""), {"id": domain_id, "org": s.org_id}).mappings().one_or_none()
    return dict(r) if r else None


def exists(s: Scope, domain_id: int) -> bool:
    return s.conn.execute(sa.text("select 1 from org_domains where id = :d"), {"d": domain_id}).first() is not None
