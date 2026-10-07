from __future__ import annotations

import uuid

import sqlalchemy as sa

from services.api.deps import Scope


def bundle(s: Scope, bundle_id: str) -> tuple[dict, list[dict]] | None:
    try:
        uuid.UUID(bundle_id)
    except ValueError:
        return None
    b = s.conn.execute(sa.text("""
        select id::text, domain_id, campaign_id::text, bundle_root, signature, collector_pk, artifact_dir, partial,
               created_at, anchored_tx, anchored_at
        from evidence_bundles where id = :id and org_id = :org"""), {"id": bundle_id, "org": s.org_id}
    ).mappings().one_or_none()
    if b is None:
        return None
    arts = s.conn.execute(sa.text("""select name, sha256, size_bytes from evidence_artifacts
                                     where bundle_id = :id and org_id = :org order by name"""),
                          {"id": bundle_id, "org": s.org_id}).mappings().all()
    return dict(b), [dict(a) for a in arts]


def latest_report(s: Scope, bundle_id: str) -> dict | None:
    r = s.conn.execute(sa.text("""select recipient, body, created_at, sent from abuse_reports
                                  where bundle_id = :id and org_id = :org order by created_at desc limit 1"""),
                       {"id": bundle_id, "org": s.org_id}).mappings().one_or_none()
    return dict(r) if r else None
