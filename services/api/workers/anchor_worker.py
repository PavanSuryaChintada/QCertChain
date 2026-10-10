"""Anchor worker: drains anchor_queue to the chain. NON-BLOCKING by design (BLOCKCHAIN.md §7).

If the chain is down, items stay queued with exponential backoff (cap 60 s) and the UI shows the depth;
detection, clustering and interdiction never wait on a transaction. AlreadyPublished / AlreadyAnchored
mean the write already landed (e.g. a retry after a lost receipt): treated as done, idempotently.

A trusted platform process across all orgs: every write is signed by the QUEUE ROW's org (its org_id),
never by a payload field, and every row it touches is addressed by primary key AND that org_id.
"""
from __future__ import annotations

import json
import time

import sqlalchemy as sa

from services.api.db import engine
from services.config import SETTINGS

IDEMPOTENT = ("AlreadyPublished", "AlreadyAnchored")
EVENT_KIND = {"evidence": "evidence_anchored", "campaign": "campaign_published", "attest": "attested",
              "corroborate": "corroborated"}


def _dispatch(c: sa.Connection, ledger, kind: str, p: dict, org_id: int, org: str) -> tuple[str, str]:
    """Returns (tx_hash, subject). `org` is the queue row's org slug: the signer."""
    if kind == "evidence":
        tx = ledger.anchor_evidence(p["bundle_id"], p["bundle_root"], p.get("campaign_id"), as_org=org)
        c.execute(sa.text("""update evidence_bundles set anchored_tx = :tx, anchored_at = now()
                             where id = :b and org_id = :o"""), {"tx": tx, "b": p["bundle_id"], "o": org_id})
        return tx, p["bundle_id"]
    if kind == "campaign":
        row = c.execute(sa.text("""select ioc_root, kit_hash, domain_count, confidence from campaigns
                                   where id = :c and org_id = :o"""), {"c": p["campaign_id"], "o": org_id}).one()
        tx = ledger.publish_campaign(p["campaign_id"], row.ioc_root, row.kit_hash, row.domain_count,
                                     round(100 * (row.confidence or 0)), as_org=org)
        c.execute(sa.text("update campaigns set published_tx = :tx where id = :c and org_id = :o"),
                  {"tx": tx, "c": p["campaign_id"], "o": org_id})
        return tx, p["campaign_id"]
    if kind == "attest":
        return ledger.attest(p["subject_hash"], p["verdict"], as_org=org), p["subject_hash"]
    if kind == "corroborate":
        return ledger.corroborate(p["chain_campaign_id"], as_org=org), p["chain_campaign_id"]
    raise ValueError(f"unknown anchor kind {kind!r}")


def process_due(c: sa.Connection, ledger, limit: int = 50) -> int:
    rows = c.execute(sa.text("""
        select q.id, q.kind, q.payload, q.attempts, q.org_id, o.slug as org from anchor_queue q
        join organisations o on o.id = q.org_id
        where not q.done and q.next_attempt_at <= now() order by q.id limit :n for update of q skip locked"""),
        {"n": limit}).mappings().all()
    done = 0
    for r in rows:
        sp = c.begin_nested()  # one item's failure never rolls back the others
        try:
            tx, subject = _dispatch(c, ledger, r["kind"], r["payload"], r["org_id"], r["org"])
            acct = getattr(ledger, "accounts", {}).get(r["org"])
            c.execute(sa.text("""insert into ledger_events (org_id, kind, tx_hash, subject, org_address, payload)
                                 values (:oid, :k, :tx, :s, :org, cast(:p as jsonb))"""),
                      {"oid": r["org_id"], "k": EVENT_KIND[r["kind"]], "tx": tx, "s": subject,
                       "org": acct.address if acct else None, "p": json.dumps(r["payload"])})
            c.execute(sa.text("update anchor_queue set done = true, last_error = null where id = :i"), {"i": r["id"]})
            sp.commit()
            done += 1
        except Exception as e:
            sp.rollback()
            msg = f"{type(e).__name__}: {e}"[:500]
            if any(x in msg for x in IDEMPOTENT):
                c.execute(sa.text("update anchor_queue set done = true, last_error = :m where id = :i"),
                          {"m": f"already on chain: {msg}", "i": r["id"]})
                done += 1
                continue
            delay = min(2 ** (r["attempts"] + 1), 60)
            c.execute(sa.text("""update anchor_queue set attempts = attempts + 1, last_error = :m,
                                 next_attempt_at = now() + make_interval(secs => :d) where id = :i"""),
                      {"m": msg, "d": delay, "i": r["id"]})
    return done


def run_once(ledger) -> int:
    try:
        with engine().begin() as c:
            return process_due(c, ledger)
    except Exception as e:  # database blip: never crash the worker
        print(f"anchor worker: {type(e).__name__}: {e}", flush=True)
        # A connection that dropped mid-batch left every later loop failing with "Can't reconnect until invalid
        # transaction is rolled back" until a restart (2026-10-10). Start again from fresh connections, as a restart
        # would; items already on chain are recognised as such on the retry.
        engine().dispose()
        return 0


def main() -> None:
    from services.api.ledger_service import Ledger
    ledger = Ledger.from_settings(SETTINGS)
    while True:
        n = run_once(ledger)
        time.sleep(0.5 if n else 2.0)


if __name__ == "__main__":
    main()
