"""Graph edges from enrichment, and campaign upsert from clusters (TRD §4)."""
from __future__ import annotations

import hashlib
import uuid
from collections import Counter

import sqlalchemy as sa

from evidence.merkle import leaf_hash, merkle_root
from services.config import SETTINGS
from services.enrich.enrichers import Enrichment
from services.graph.cluster import cluster

# How strongly a shared attribute implies the same operator (TRD §4; registrar: spec D9).
EDGE_WEIGHTS = {"kit_hash": 1.0, "favicon_hash": 0.85, "ip": 0.80, "nameserver": 0.60, "asn": 0.35,
                "cert_issuer": 0.15, "registrar": 0.15}
# Takedown targets are ip / nameserver / registrar only (spec D9).
TAKEDOWN_ROUTE = {"ip": "hosting", "nameserver": "dns", "registrar": "registrar"}


def edges_for(e: Enrichment) -> list[tuple[str, str, float]]:
    out: list[tuple[str, str, float]] = [("ip", ip, EDGE_WEIGHTS["ip"]) for ip in e.ip_addresses]
    out += [("nameserver", ns.lower().rstrip("."), EDGE_WEIGHTS["nameserver"]) for ns in e.nameservers]
    if e.asn is not None:
        out.append(("asn", str(e.asn), EDGE_WEIGHTS["asn"]))
    for kind, val in (("cert_issuer", e.cert_issuer), ("registrar", e.registrar), ("kit_hash", e.dom_hash),
                      ("favicon_hash", e.favicon_hash)):
        if val:
            out.append((kind, val, EDGE_WEIGHTS[kind]))
    return out


def ioc_root(iocs: list[str]) -> str:
    """Merkle root over the sorted IOC set. Only this root goes on-chain, never the list (BLOCKCHAIN §2)."""
    return merkle_root([leaf_hash(i, hashlib.sha256(i.encode()).digest()) for i in sorted(set(iocs))]).hex()


def recluster(c: sa.Connection) -> list[str]:
    """Cluster all confirmed domains and upsert campaigns. Campaign ids are stable across runs: a cluster
    reuses the campaign most of its members already belong to. Returns campaign ids (largest first)."""
    edges = [(r.domain_id, r.node_id, r.weight) for r in c.execute(sa.text("""
        select e.domain_id, e.node_id, e.weight from graph_edges e
        join domains d on d.id = e.domain_id where d.status = 'confirmed'"""))]
    clusters = cluster(edges, threshold=SETTINGS.cluster_edge_threshold)
    if not clusters:
        return []
    member_ids = sorted({d for cl in clusters for d in cl.domain_ids})
    dom = {r.id: r for r in c.execute(sa.text(
        "select id, name, campaign_id, brand_matched from domains where id = any(:ids)"), {"ids": member_ids})}
    node_ids = sorted({n for cl in clusters for n in cl.node_ids})
    nodes = {r.id: r for r in c.execute(sa.text("select id, kind, value from infra_nodes where id = any(:ids)"),
                                        {"ids": node_ids})}
    n_existing = c.execute(sa.text("select count(*) from campaigns")).scalar_one()
    used: set[str] = set()
    out: list[str] = []
    for cl in clusters:
        prior = Counter(str(dom[d].campaign_id) for d in cl.domain_ids if dom[d].campaign_id)
        cid = next((k for k, _ in prior.most_common() if k not in used), None)
        kit = Counter(nodes[n].value for n in cl.node_ids if nodes[n].kind == "kit_hash").most_common(1)
        brands = sorted({dom[d].brand_matched for d in cl.domain_ids if dom[d].brand_matched})
        iocs = [f"domain:{dom[d].name}" for d in cl.domain_ids] + [f"{nodes[n].kind}:{nodes[n].value}" for n in cl.node_ids]
        params = {"kit": kit[0][0] if kit else None, "dc": len(cl.domain_ids), "ic": len(cl.node_ids),
                  "conf": cl.confidence, "brands": brands, "root": ioc_root(iocs)}
        if cid is None:
            n_existing += 1
            cid = str(uuid.uuid4())
            c.execute(sa.text("""insert into campaigns (id, label, kit_hash, domain_count, infra_count, confidence,
                                 brands, ioc_root) values (:id, :label, :kit, :dc, :ic, :conf, :brands, :root)"""),
                      {**params, "id": cid, "label": f"CAMP-{n_existing:04d}"})
        else:
            c.execute(sa.text("""update campaigns set kit_hash = :kit, domain_count = :dc, infra_count = :ic,
                                 confidence = :conf, brands = :brands, ioc_root = :root, last_seen = now()
                                 where id = :id"""), {**params, "id": cid})
        c.execute(sa.text("""update domains set campaign_id = :cid,
                             campaign_joined_at = case when campaign_id is distinct from :cid then now()
                                                       else campaign_joined_at end
                             where id = any(:ids)"""), {"cid": cid, "ids": sorted(cl.domain_ids)})
        used.add(cid)
        out.append(cid)
    return out
