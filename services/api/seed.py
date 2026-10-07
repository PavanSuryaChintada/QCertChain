"""Seeded demo campaign (DATA.md §6, synthetic fallback). Everything it creates is labelled source='seed'.

Safety: every domain, nameserver and contact uses the reserved `.example` TLD (RFC 2606) and every IP is in
an RFC 5737 documentation range, every ASN in the RFC 5398 documentation range. A seed can never name or
accuse a real business. Pages are rendered from one kit template (identical tag structure, varying strings)
and run through the REAL confirmation rules — the verdicts are computed, not asserted.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sqlalchemy as sa

from services.api import repo
from services.api.pipeline import insert_bundles, prepare_bundle
from services.config import SETTINGS
from services.enrich.confirm import analyze_page
from services.enrich.enrichers import Enrichment
from services.enrich.fetch import FetchedPage
from services.enrich.fingerprint import kit_hash as page_kit_hash
from services.graph.build import edges_for, recluster
from services.graph.snapshot import build_sweep
from services.ingest.brands import load_brands
from services.ingest.triage import triage

TEMPLATE = (Path(__file__).parent / "kit_template.html").read_text(encoding="utf-8")
DOC_NETS = ("198.51.100.", "203.0.113.")   # RFC 5737
DOC_ASNS = (64496, 64497, 64498, 64499, 64500, 64501)  # RFC 5398
COLLECTOR = "192.0.2.77"                    # RFC 5737: where the kit posts credentials
SHARED_DNS = "ns.shared-dns-provider.example"  # big shared DNS host: not attacker infra, never a node
WORDS = ("verify", "kyc", "secure", "update", "netbanking", "login", "account", "alert")
PALETTE = ("#b02a30", "#004c8f", "#97144d", "#ed1c24", "#0b5394", "#6aa84f")


def _zipf(rng: random.Random, items: list, s: float = 1.3):
    return rng.choices(items, weights=[1 / (i + 1) ** s for i in range(len(items))])[0]


def seed_campaign(c: sa.Connection, *, label: str, domains: int = 400, ips: int = 12, asns: int = 3,
                  nameservers: int = 4, registrars: int = 3, brands: list[str] | None = None,
                  shared_dns_fraction: float = 0.08, seed: int = 42,
                  evidence_dir: Path | str | None = None, signing_key_hex: str | None = None,
                  ip_base: int = 10, shared_ips: list[str] | None = None,
                  shared_nameservers: list[str] | None = None) -> str:
    """shared_ips / shared_nameservers: infrastructure deliberately reused from another org's seeded campaign
    (listed first, so the Zipf draw puts the most domains on it). Same safety rules: documentation IPs and
    reserved .example names only."""
    rng = random.Random(f"{label}:{seed}")
    evidence_dir = evidence_dir or SETTINGS.evidence_dir
    key = signing_key_hex or SETTINGS.collector_private_key
    idx = load_brands(SETTINGS.brands_file)
    chosen = [b for b in idx.brands if b.name in (brands or ["ICICI Bank"])] or [idx.brands[0]]
    slug = "".join(ch for ch in label.lower() if ch.isalnum() or ch == "-") or "seed"

    shared_ips, shared_nameservers = list(shared_ips or []), list(shared_nameservers or [])
    if not all(ip.startswith(DOC_NETS) for ip in shared_ips):
        raise ValueError("shared_ips must be RFC 5737 documentation addresses")
    if not all(ns.endswith(".example") for ns in shared_nameservers):
        raise ValueError("shared_nameservers must use the reserved .example TLD")
    ip_list = shared_ips + [f"{DOC_NETS[i % 2]}{ip_base + i}" for i in range(ips)]
    ip_list = list(dict.fromkeys(ip_list))
    asn_of = {ip: DOC_ASNS[i % max(1, min(asns, len(DOC_ASNS)))] for i, ip in enumerate(ip_list)}
    ns_list = list(dict.fromkeys(shared_nameservers + [f"ns{i + 1}.{slug}-dns.example" for i in range(nameservers)]))
    reg_list = [f"Registrar {chr(65 + i)} (seed)" for i in range(registrars)]
    kit_label = f"{slug} (seed kit)"

    sample = TEMPLATE.format(brand="X", bg="#fff", accent="#000", slug="x", tagline="x", collector=COLLECTOR, ref="x")
    kit_hash = page_kit_hash(sample)
    assert kit_hash, "seed kit template must clear the kit complexity floor"
    repo.add_known_kit(c, kit_hash, kit_label, "seed")
    known = repo.known_kits(c)
    now = datetime.now(timezone.utc)

    rows, staged = [], []  # staged: (name, result, page, enrichment)
    seen_names: set[str] = set()
    while len(staged) < domains:
        brand = rng.choice(chosen)
        token = max(brand.tokens, key=len) if rng.random() < 0.5 else brand.tokens[0]
        name = f"{token}-{rng.choice(WORDS)}-{rng.choice(WORDS)}-{rng.randint(1, 9999)}.example"
        if name in seen_names:
            continue
        seen_names.add(name)
        html = TEMPLATE.format(brand=brand.name, bg=rng.choice(("#f4f4f4", "#ffffff", "#eef2f7")),
                               accent=rng.choice(PALETTE), slug=token, tagline=rng.choice(("Hum Hai Na", "Secure", "")),
                               collector=COLLECTOR, ref=f"{label}-{rng.randint(1, 99999)}")
        page = FetchedPage(f"https://{name}/", f"https://{name}/login", 200, html,
                           {"x-qcertchain-seed": "synthetic"}, [f"https://{name}/"], None, None, [], "httpx")
        ip = _zipf(rng, ip_list)
        ns = [] if rng.random() < shared_dns_fraction else [_zipf(rng, ns_list)]  # shared DNS: not attacker infra
        reg_at = now - timedelta(days=rng.randint(1, 20))
        e = Enrichment(ip_addresses=[ip], asn=asn_of[ip], asn_name=f"DOC-AS{asn_of[ip]} (seed)", country="ZZ",
                       nameservers=ns or [SHARED_DNS], registrar=_zipf(rng, reg_list),
                       abuse_email=None, registered_at=reg_at, dom_hash=page_kit_hash(html),
                       cert_issuer="Let's Encrypt", partial=True, errors={"seed": "synthetic: no screenshot, no TLS"})
        result = analyze_page(page, name, brand, known, {}, reg_at, "Let's Encrypt", now=now)
        t = triage(name)
        rows.append({"name": name, "etld1": t.etld1, "source": "seed", "ct_seen_at": reg_at,
                     "triage_score": t.score, "triage_reasons": repo.triage_doc(t), "brand_matched": brand.name,
                     "status": result.verdict if result.verdict != "candidate" else "candidate",
                     "confirm_reasons": result.reasons(), "confidence": result.confidence})
        staged.append((name, result, page, e))

    ids = repo.bulk_insert_domains(c, rows)
    repo.bulk_save_enrichment(c, [(ids[n], e) for n, _, _, e in staged if n in ids])
    edge_specs = [(ids[n], kind, value, w) for n, r, _, e in staged if n in ids and r.verdict == "confirmed"
                  for kind, value, w in edges_for(e) if value != SHARED_DNS]
    node_ids = repo.bulk_upsert_nodes(c, {(k, v) for _, k, v, _ in edge_specs})
    repo.bulk_add_edges(c, [(d, node_ids[(k, v)], w) for d, k, v, w in edge_specs])

    campaign_ids = recluster(c)
    camp = {r.id: r for r in c.execute(sa.text(
        "select d.id, d.campaign_id, c.label from org_domains d left join campaigns c on c.id = d.campaign_id "
        "where d.id = any(:ids)"), {"ids": sorted(ids.values())})}
    prepared = [prepare_bundle(ids[n], n, r, pg, e,
                               campaign_id=str(camp[ids[n]].campaign_id) if camp[ids[n]].campaign_id else None,
                               campaign_label=camp[ids[n]].label, evidence_dir=evidence_dir, signing_key_hex=key,
                               source="seed")
                for n, r, pg, e in staged if n in ids and r.verdict == "confirmed"]
    insert_bundles(c, prepared)
    cid = camp[ids[staged[0][0]]].campaign_id
    build_sweep(c, str(cid))  # seeded campaigns are demo-ready: the whole budget sweep is precomputed
    repo.log(c, "system", f"seeded campaign '{label}': {len(ids)} domains (source=seed, synthetic)",
             context={"campaign_id": str(cid), "campaigns_after_recluster": len(campaign_ids)})
    return str(cid)
