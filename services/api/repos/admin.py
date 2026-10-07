"""Platform-admin operations. The admin key holds no org; each operation names its target org explicitly and
runs under that org's row-level security, so even admin writes cannot land in the wrong tenant."""
from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa

from services.api.db import bind_org, unbind_org
from services.api.seed import seed_campaign


def org_id(c: sa.Connection, slug: str) -> int | None:
    return c.execute(sa.text("select id from organisations where slug = :s"), {"s": slug}).scalar()


def seed(c: sa.Connection, *, org: int, evidence_dir: Path | str, signing_key_hex: str, **kw) -> dict:
    bind_org(c, org)
    try:
        cid = seed_campaign(c, evidence_dir=evidence_dir, signing_key_hex=signing_key_hex, **kw)
        n = c.execute(sa.text("select domain_count from campaigns where id = :c"), {"c": cid}).scalar()
    finally:
        unbind_org(c)
    return {"campaign_id": cid, "domains": n}  # an acknowledgement, not the campaign: admin reads no org data
