from __future__ import annotations

import sqlalchemy as sa

from services.api import repo
from services.api.deps import Scope


def queue_depth(s: Scope) -> int:
    return s.conn.execute(sa.text("select count(*) from anchor_queue where org_id = :org and not done"),
                          {"org": s.org_id}).scalar_one()


def enqueue(s: Scope, kind: str, payload: dict) -> None:
    """The signing org is the KEY's org, never a request field: an org cannot write as another org."""
    repo.enqueue_anchor(s.conn, kind, {**payload, "as_org": s.org_slug})
    repo.log(s.conn, "ledger", f"queued {kind}", context=payload)


def events(s: Scope, *, limit: int, after: list | None) -> list[dict]:
    """This org's own ledger writes (the local index of what it put on chain). Keyset on id desc."""
    return [dict(r) for r in s.conn.execute(sa.text("""
        select id, kind, tx_hash, block_number, subject, org_address, payload, observed_at from ledger_events
        where org_id = :org and (cast(:ai as bigint) is null or id < :ai)
        order by id desc limit :l"""), {"org": s.org_id, "ai": after[0] if after else None, "l": limit + 1}).mappings()]


def published_subjects(s: Scope) -> list[str]:
    """This org's own published campaign ids, to label chain results it recognises. Other orgs' chain records
    stay as bare chain ids: the chain is shared, the mapping to local rows is not."""
    return list(s.conn.execute(sa.text("""select subject from ledger_events
                                          where kind = 'campaign_published' and org_id = :org"""),
                               {"org": s.org_id}).scalars())
