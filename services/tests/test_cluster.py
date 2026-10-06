import random
import time
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

from services.enrich.enrichers import Enrichment
from services.graph.build import EDGE_WEIGHTS, TAKEDOWN_ROUTE, edges_for
from services.graph.cluster import cluster


def test_weights_and_routes_are_the_spec_values():
    assert EDGE_WEIGHTS == {"kit_hash": 1.0, "favicon_hash": 0.85, "ip": 0.80, "nameserver": 0.60, "asn": 0.35,
                            "cert_issuer": 0.15, "registrar": 0.15}
    assert TAKEDOWN_ROUTE == {"ip": "hosting", "nameserver": "dns", "registrar": "registrar"}


def test_edges_for_enrichment():
    e = Enrichment(ip_addresses=["203.0.113.9"], asn=64500, nameservers=["ns1.x.top"], cert_issuer="Let's Encrypt",
                   registrar="NameSilo, LLC", dom_hash="abc", favicon_hash="-123")
    got = set(edges_for(e))
    assert got == {("ip", "203.0.113.9", 0.8), ("asn", "64500", 0.35), ("nameserver", "ns1.x.top", 0.6),
                   ("cert_issuer", "Let's Encrypt", 0.15), ("registrar", "NameSilo, LLC", 0.15),
                   ("kit_hash", "abc", 1.0), ("favicon_hash", "-123", 0.85)}


def test_shared_kit_clusters():
    cs = cluster([(1, 100, 1.0), (2, 100, 1.0), (3, 101, 0.8)])
    assert len(cs) == 1 and cs[0].domain_ids == {1, 2} and cs[0].confidence == 1.0


def test_shared_asn_or_issuer_alone_never_merges():
    e = [(1, 200, 0.35), (2, 200, 0.35), (1, 300, 0.15), (2, 300, 0.15), (3, 300, 0.15)]
    assert cluster(e) == []


def test_merge_on_two_medium_edges():
    e = [(1, 10, 1.0), (2, 10, 1.0), (3, 11, 1.0), (4, 11, 1.0),
         (1, 20, 0.35), (3, 20, 0.35), (2, 21, 0.35), (4, 21, 0.35)]
    assert [c.domain_ids for c in cluster(e)] == [{1, 2, 3, 4}]


def test_one_medium_edge_does_not_merge():
    e = [(1, 10, 1.0), (2, 10, 1.0), (3, 11, 1.0), (4, 11, 1.0), (1, 20, 0.35), (3, 20, 0.35)]
    assert sorted(sorted(c.domain_ids) for c in cluster(e)) == [[1, 2], [3, 4]]


def test_cluster_node_ids_include_weak_infrastructure():
    cs = cluster([(1, 100, 1.0), (2, 100, 1.0), (1, 500, 0.15)])
    assert cs[0].node_ids == {100, 500}


def test_500_domains_under_2s():
    rng = random.Random(0)
    e = [(d, 1000 + rng.randint(0, 40), rng.choice([1.0, 0.8, 0.6, 0.35, 0.15])) for d in range(500) for _ in range(4)]
    t = time.perf_counter()
    cluster(e)
    assert time.perf_counter() - t < 2.0


@pytest.mark.db
def test_recluster_creates_stable_labelled_campaign_with_ioc_root(db):
    from services.api import repo
    from services.enrich.confirm import ConfirmResult, Signal
    from services.graph.build import recluster
    from services.ingest.triage import triage
    ids = []
    for n in ["sbi-kyc-a.top", "sbi-kyc-b.top", "lonely-sbi-kyc.top"]:
        t = triage(n)
        d, _ = repo.upsert_candidate(db, name=n, etld1=t.etld1, cert_id=None, triage=t, source="seed",
                                     ct_seen_at=datetime.now(timezone.utc))
        repo.set_confirmation(db, d, ConfirmResult("confirmed", 0.9, [Signal("a", "strong", "x"), Signal("b", "strong", "y")], 2))
        ids.append(d)
    kit = repo.upsert_node(db, "kit_hash", "abc")
    ip = repo.upsert_node(db, "ip", "203.0.113.9")
    for d in ids[:2]:
        repo.add_edge(db, d, kit, 1.0)
        repo.add_edge(db, d, ip, 0.8)
    first = recluster(db)
    assert len(first) == 1
    row = db.execute(sa.text("select label, domain_count, kit_hash, ioc_root, confidence from campaigns")).one()
    assert row.label == "CAMP-0001" and row.domain_count == 2 and row.kit_hash == "abc" and len(row.ioc_root) == 64
    members = db.execute(sa.text("select count(*) from domains where campaign_id is not null and campaign_joined_at is not null")).scalar()
    assert members == 2
    assert recluster(db) == first  # stable id on re-run


def test_shared_cdn_and_dns_infrastructure_makes_no_edges():
    """Review I6: two unrelated sites behind Cloudflare share anycast IPs, the ASN and the NS provider.
    None of that implies one operator, so none of it becomes a clustering edge."""
    e = Enrichment(ip_addresses=["104.21.5.6"], asn=13335, nameservers=["lara.ns.cloudflare.com",
                   "ns-123.awsdns-15.com", "ns1.x.top"], registrar="NameSilo, LLC", dom_hash="abc")
    got = set(edges_for(e))
    assert not {k for k, *_ in got} & {"ip", "asn"}
    assert {v for k, v, _ in got if k == "nameserver"} == {"ns1.x.top"}
    assert ("kit_hash", "abc", 1.0) in got


def test_two_unrelated_cloudflare_sites_never_merge():
    a = Enrichment(ip_addresses=["104.21.5.6"], asn=13335, nameservers=["lara.ns.cloudflare.com"], dom_hash="k1")
    b = Enrichment(ip_addresses=["104.21.5.6"], asn=13335, nameservers=["lara.ns.cloudflare.com"], dom_hash="k2")
    ids: dict[tuple, int] = {}
    edges = [(d, ids.setdefault((k, v), len(ids) + 100), w) for d, e in ((1, a), (2, b)) for k, v, w in edges_for(e)]
    assert cluster(edges) == []
