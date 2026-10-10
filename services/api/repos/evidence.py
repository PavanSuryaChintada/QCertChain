from __future__ import annotations

import uuid

import sqlalchemy as sa

from services.api.deps import Scope


def recent(s: Scope, limit: int) -> list[dict]:
    """This organisation's newest bundles, with the domain each one is for (the Evidence page lists them)."""
    rows = s.conn.execute(sa.text("""
        select b.id::text as bundle_id, d.name as domain, b.campaign_id::text as campaign_id, b.created_at,
               b.anchored_tx is not null as anchored, b.partial
        from evidence_bundles b left join domains d on d.id = b.domain_id
        where b.org_id = :org order by b.created_at desc, b.id limit :n"""), {"org": s.org_id, "n": limit})
    return [dict(r) for r in rows.mappings()]


def bundle(s: Scope, bundle_id: str) -> tuple[dict, list[dict]] | None:
    """The bundle and its artifact hashes in one statement."""
    try:
        uuid.UUID(bundle_id)
    except ValueError:
        return None
    b = s.conn.execute(sa.text("""
        select b.id::text, b.domain_id, b.campaign_id::text, b.bundle_root, b.signature, b.collector_pk, b.artifact_dir,
               b.partial, b.created_at, b.anchored_tx, b.anchored_at,
               (select coalesce(json_agg(json_build_object('name', a.name, 'sha256', a.sha256,
                                                           'size_bytes', a.size_bytes) order by a.name), '[]'::json)
                  from evidence_artifacts a where a.bundle_id = b.id and a.org_id = :org) as artifacts
        from evidence_bundles b where b.id = :id and b.org_id = :org"""), {"id": bundle_id, "org": s.org_id}
    ).mappings().one_or_none()
    if b is None:
        return None
    b = dict(b)
    return b, b.pop("artifacts")


def latest_report(s: Scope, bundle_id: str) -> dict | None:
    try:
        uuid.UUID(bundle_id)
    except ValueError:
        return None
    r = s.conn.execute(sa.text("""select recipient, body, created_at, sent from abuse_reports
                                  where bundle_id = :id and org_id = :org order by created_at desc limit 1"""),
                       {"id": bundle_id, "org": s.org_id}).mappings().one_or_none()
    return dict(r) if r else None
