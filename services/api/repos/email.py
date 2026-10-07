from __future__ import annotations

import uuid

import sqlalchemy as sa

from services.api.deps import Scope
from services.email.analyze import EmailVerdict, analyze, db_lookup, persist_and_correlate
from services.ingest.brands import BrandIndex

_SELECT = """select id::text, source, verdict, strong_count, from_addr, from_etld1, reply_to_etld1, return_path_etld1,
                    auth_results, received_hops, urls, signals, linked_campaign_ids::text[] as linked_campaign_ids,
                    linked_domain_ids, received_at from email_analyses"""


def analyze_and_store(s: Scope, raw: bytes, source: str, brands: BrandIndex) -> tuple[EmailVerdict, str, list[int]]:
    v = analyze(raw, brands=brands, lookup=db_lookup(s.conn))
    aid, new_ids = persist_and_correlate(s.conn, v, source)
    return v, aid, new_ids


def list_(s: Scope, *, verdict: str | None, limit: int, after: list | None) -> list[dict]:
    """Keyset on (received_at, id) desc; returns limit + 1 rows."""
    return [dict(r) for r in s.conn.execute(sa.text(_SELECT + """ where org_id = :org
            and (cast(:v as text) is null or verdict = :v)
            and (cast(:ar as timestamptz) is null or (received_at, id) < (cast(:ar as timestamptz), cast(:ai as uuid)))
            order by received_at desc, id desc limit :l"""),
            {"org": s.org_id, "v": verdict, "l": limit + 1, "ar": after[0] if after else None,
             "ai": after[1] if after else None}).mappings()]


def get(s: Scope, analysis_id: str) -> dict | None:
    try:
        uuid.UUID(analysis_id)
    except ValueError:
        return None
    r = s.conn.execute(sa.text(_SELECT + " where id = :i and org_id = :org"),
                       {"i": analysis_id, "org": s.org_id}).mappings().one_or_none()
    return dict(r) if r else None
