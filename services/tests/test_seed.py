import pytest
import sqlalchemy as sa

from services.api.seed import seed_campaign

pytestmark = pytest.mark.db


def test_seed_clusters_into_one_labelled_campaign(db, tmp_path):
    cid = seed_campaign(db, label="titli-kit", domains=400, evidence_dir=tmp_path)
    n = db.execute(sa.text("select count(*) from domains where campaign_id=:c and source='seed' and status='confirmed'"),
                   {"c": cid}).scalar()
    assert n == 400
    assert db.execute(sa.text("select count(*) from campaigns")).scalar() == 1
    kinds = dict(db.execute(sa.text("select kind, count(*) from infra_nodes group by kind")).all())
    assert kinds["ip"] == 12 and kinds["nameserver"] == 4 and kinds["registrar"] == 3 and kinds["kit_hash"] == 1
    assert db.execute(sa.text("select count(*) from evidence_bundles where campaign_id=:c"), {"c": cid}).scalar() == 400


def test_every_seed_domain_has_two_strong_reasons(db, tmp_path):
    seed_campaign(db, label="t2", domains=20, evidence_dir=tmp_path)
    rows = db.execute(sa.text("select confirm_reasons from domains where source='seed'")).scalars().all()
    assert len(rows) == 20 and all(sum(s["strength"] == "strong" for s in r["signals"]) >= 2 for r in rows)


def test_seed_uses_only_reserved_names_and_documentation_addresses(db, tmp_path):
    import ipaddress
    seed_campaign(db, label="t3", domains=50, evidence_dir=tmp_path)
    assert all(n.endswith(".example") for n in db.execute(sa.text("select name from domains")).scalars())
    docs = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
    for v in db.execute(sa.text("select value from infra_nodes where kind='ip'")).scalars():
        assert any(ipaddress.ip_address(v) in net for net in docs), v
    for v in db.execute(sa.text("select value from infra_nodes where kind in ('nameserver','registrar')")).scalars():
        assert v.endswith(".example") or "(seed)" in v, v


def test_shared_dns_provider_is_not_a_takedown_node(db, tmp_path):
    seed_campaign(db, label="t4", domains=200, evidence_dir=tmp_path, shared_dns_fraction=0.1)
    assert db.execute(sa.text("select count(*) from infra_nodes where value like '%shared-dns%'")).scalar() == 0


def test_seed_is_deterministic(db, tmp_path):
    seed_campaign(db, label="t5", domains=30, evidence_dir=tmp_path, seed=7)
    a = sorted(db.execute(sa.text("select name from domains")).scalars())
    db.execute(sa.text("truncate domains, campaigns, infra_nodes, graph_edges, evidence_bundles, known_kits cascade"))
    seed_campaign(db, label="t5", domains=30, evidence_dir=tmp_path / "b", seed=7)
    assert sorted(db.execute(sa.text("select name from domains")).scalars()) == a


def test_seed_is_bulk_not_per_row(db, tmp_path):
    """Supabase round trip from the demo machine is ~110 ms: 400 domains x ~26 statements would take
    ~19 minutes. The seed must write in bulk regardless of size."""
    import sqlalchemy.event as ev
    count = {"n": 0}

    def tick(*a, **kw):
        count["n"] += 1

    ev.listen(db, "before_cursor_execute", tick)
    try:
        seed_campaign(db, label="bulk", domains=400, evidence_dir=tmp_path)
    finally:
        ev.remove(db, "before_cursor_execute", tick)
    assert count["n"] < 40, count["n"]
