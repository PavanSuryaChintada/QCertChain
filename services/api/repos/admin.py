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


# The known-good demo state (DEMO.md): Bank One's 400-domain ICICI-themed campaign, and Bank Two's 50-domain
# HDFC-themed campaign on the same kit, sharing Bank One's top hosting IP and first nameserver. Deterministic:
# every reset produces the same names, the same infrastructure, the same plans.
DEMO_SEEDS = (
    # 400 on the main clusters + 40 long-tail domains (own IP, shared DNS, 8 small registrars) + 30 unreachable
    # (shared DNS only). Measured with CP-SAT: k=5 covers 382 of 470 with a nameserver+registrar mix, the knee is near
    # k=4-6, and 30 can never be reached. Plans change composition as k grows (not nested). A real tradeoff.
    ("org1", dict(label="titli-kit", domains=400, ips=12, asns=3, nameservers=4, registrars=10, brands=["ICICI Bank"],
                  tail_domains=40, tail_registrars=8, unreachable_domains=30)),
    ("org2", dict(label="hdfc-kit", domains=50, ips=6, asns=2, nameservers=3, registrars=3, brands=["HDFC Bank"],
                  ip_base=100, shared_ips=["198.51.100.10"], shared_nameservers=["ns1.titli-kit-dns.example"])),
)


def reset_demo(c: sa.Connection, *, evidence_dir: Path | str, signing_key_hex: str) -> dict:
    """Remove ONLY demo data (seeded domains and everything derived from them, sample emails) for every org, then
    re-seed DEMO_SEEDS. One transaction: a failure leaves the previous state intact. Live CT candidates and their
    verdicts are never touched. Returns counts only (the admin key reads no org data)."""
    removed = {"domains": 0, "campaigns": 0, "emails": 0}
    orgs = dict(c.execute(sa.text("select slug, id from organisations")).all())
    for slug, oid in orgs.items():
        p = {"o": oid}
        removed["emails"] += c.execute(sa.text(
            "delete from email_analyses where org_id = :o and source = 'sample'"), p).rowcount
        removed["domains"] += c.execute(sa.text(
            "delete from domains where origin_org_id = :o and source = 'seed'"), p).rowcount  # cascades
        # campaigns left with no member (all were seed domains) go too, with their plans, snapshots, benchmarks
        removed["campaigns"] += c.execute(sa.text("""
            delete from campaigns c where c.org_id = :o and not exists (
              select 1 from domain_verdicts v where v.org_id = :o and v.campaign_id = c.id)"""), p).rowcount
        c.execute(sa.text("""delete from infra_nodes n where n.org_id = :o and not exists (
                               select 1 from graph_edges e where e.node_id = n.id)"""), p)
        c.execute(sa.text("delete from known_kits where org_id = :o and source = 'seed'"), p)
        c.execute(sa.text("""delete from anchor_queue q where q.org_id = :o and not q.done and (
                               (q.kind = 'evidence' and not exists (select 1 from evidence_bundles b
                                  where b.id::text = q.payload->>'bundle_id'))
                            or (q.kind = 'campaign' and not exists (select 1 from campaigns x
                                  where x.id::text = q.payload->>'campaign_id')))"""), p)
    seeded = {}
    for slug, kw in DEMO_SEEDS:
        seeded[slug] = seed(c, org=orgs[slug], evidence_dir=evidence_dir, signing_key_hex=signing_key_hex, **kw)
    return {"removed": removed, "seeded": seeded}
