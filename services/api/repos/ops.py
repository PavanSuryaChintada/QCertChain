from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from services.api.deps import Scope


def metrics(s: Scope) -> dict:
    return dict(s.conn.execute(sa.text("""
        select (select count(*) from campaigns where org_id = :org and status = 'active') as campaigns_active,
               (select count(*) from domain_verdicts where org_id = :org and status = 'confirmed') as domains_confirmed,
               (select count(*) from org_domains where status = 'candidate') as domains_candidate,
               (select count(*) from interdiction_plans where org_id = :org
                  and created_at > now() - interval '1 day') as plans_today,
               (select count(*) from evidence_bundles where org_id = :org
                  and created_at > now() - interval '1 day') as bundles_today,
               (select count(*) from anchor_queue where org_id = :org and not done) as anchor_queue_depth"""),
        {"org": s.org_id}).mappings().one())


def status_counts(s: Scope) -> dict:
    """Everything the console's status bar and architecture page need from the database, in ONE statement."""
    return dict(s.conn.execute(sa.text("""
        select (select name from organisations where id = :org) as org_name,
               (select count(*) from campaigns where org_id = :org and status = 'active') as campaigns_active,
               (select count(*) from domain_verdicts where org_id = :org and status = 'confirmed') as domains_confirmed,
               (select count(*) from org_domains where status = 'candidate') as domains_candidate,
               (select count(*) from org_domains where candidate_at > now() - interval '1 hour') as candidates_last_hour,
               (select count(*) from domain_verdicts where org_id = :org
                  and confirmed_at > now() - interval '1 hour') as confirmations_last_hour,
               (select count(*) from interdiction_plans where org_id = :org
                  and created_at > now() - interval '1 day') as plans_today,
               (select count(*) from evidence_bundles where org_id = :org
                  and created_at > now() - interval '1 day') as bundles_today,
               (select count(*) from evidence_bundles where org_id = :org) as bundles_total,
               (select count(*) from anchor_queue where org_id = :org and not done) as anchor_queue_depth,
               (select count(*) from campaigns c where c.org_id = :org and not exists (
                  select 1 from campaign_snapshots x where x.campaign_id = c.id and x.org_id = :org)) as campaigns_without_graph,
               (select count(*) from email_analyses where org_id = :org) as email_analyses"""),
        {"org": s.org_id}).mappings().one())


def log_page(s: Scope, *, since: datetime | None, channel: str | None, limit: int, after: list | None) -> list[dict]:
    """Platform messages (org_id null: the shared feed) and this org's own. Never another org's.
    Keyset on id desc; returns limit + 1 rows."""
    return [dict(r) for r in s.conn.execute(sa.text("""
        select id, at, channel, severity, message, context from ops_log
        where (org_id is null or org_id = :org)
          and (cast(:since as timestamptz) is null or at > :since) and (cast(:ch as text) is null or channel = :ch)
          and (cast(:ai as bigint) is null or id < :ai)
        order by id desc limit :limit"""),
        {"org": s.org_id, "since": since, "ch": channel, "limit": limit + 1,
         "ai": after[0] if after else None}).mappings()]
