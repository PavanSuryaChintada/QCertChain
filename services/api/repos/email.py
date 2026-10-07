from __future__ import annotations

import uuid

import sqlalchemy as sa

from services.api.deps import Scope
from services.email.analyze import EmailVerdict, analyze, db_lookup, persist_and_correlate
from services.ingest.brands import BrandIndex

_SELECT = """select id::text, source, verdict, strong_count, from_addr, from_etld1, reply_to_etld1, return_path_etld1,
                    auth_results, received_hops, urls, signals, linked_campaign_ids::text[] as linked_campaign_ids,
                    linked_domain_ids, received_at, count(*) over () as total from email_analyses"""


def analyze_and_store(s: Scope, raw: bytes, source: str, brands: BrandIndex) -> tuple[EmailVerdict, str, list[int]]:
    v = analyze(raw, brands=brands, lookup=db_lookup(s.conn))
    aid, new_ids = persist_and_correlate(s.conn, v, source)
    return v, aid, new_ids


def list_(s: Scope, *, verdict: str | None, limit: int, offset: int) -> list[dict]:
    return [dict(r) for r in s.conn.execute(sa.text(_SELECT + """ where org_id = :org
            and (cast(:v as text) is null or verdict = :v) order by received_at desc limit :l offset :o"""),
            {"org": s.org_id, "v": verdict, "l": limit, "o": offset}).mappings()]


def get(s: Scope, analysis_id: str) -> dict | None:
    try:
        uuid.UUID(analysis_id)
    except ValueError:
        return None
    r = s.conn.execute(sa.text(_SELECT + " where id = :i and org_id = :org"),
                       {"i": analysis_id, "org": s.org_id}).mappings().one_or_none()
    return dict(r) if r else None
