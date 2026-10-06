"""Measure everything the technical report states (spec §4.2) -> reports/metrics.json.

Every metric records value, n, dataset, method and measured_at — or {"unavailable": reason}. Nothing is
estimated. Balanced-set precision is never computed (MODELS.md §0). Run after the live pipeline has run.

    PYTHONPATH=. python -m scripts.evaluate [--since ISO] [--only section,section]
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import statistics
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from services.config import ROOT, SETTINGS

NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731
OUT = ROOT / "reports/metrics.json"


def pct(xs: list[float], q: float) -> float | None:
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))], 3) if xs else None


def section(fn):
    def wrapped(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:  # a failed section is reported as unavailable, never guessed
            return {"unavailable": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(limit=2)}
    wrapped.__name__ = fn.__name__
    return wrapped


# ---- triage (the deployed rules) -------------------------------------------------------------------------
@section
def triage_rules():
    from services.ingest.triage import triage, warm
    from services.ml.split import temporal_split
    warm()
    d = ROOT / "data/ml"
    with open(d / "positives.csv", encoding="utf-8") as f:
        pos = [{"etld1": r["etld1"], "seen": datetime.fromisoformat(r["seen"])} for r in csv.DictReader(f)]
    seen = sorted(r["seen"] for r in pos)
    _, test = temporal_split(pos, seen[int(len(seen) * 0.67)])
    neg = (d / "negatives.txt").read_text(encoding="utf-8").split()[-60000:]
    hard = (d / "hard_negatives.txt").read_text(encoding="utf-8").split()
    from services.ingest.brands import load_brands
    idx = load_brands(SETTINGS.brands_file)
    brandish = {"brand_token_exact", "lookalike", "homoglyph_hit"}
    ours = [r for r in pos if any(x.feature in brandish for x in triage(r["etld1"]).reasons)]
    tpr = sum(triage(r["etld1"]).is_candidate for r in test) / len(test)
    tpr_ours = sum(triage(r["etld1"]).is_candidate for r in ours) / len(ours) if ours else None
    fpr = sum(triage(x).is_candidate for x in neg) / len(neg)
    hfp = sum(triage(x).is_candidate for x in hard) / len(hard)
    prec = tpr * 0.001 / (tpr * 0.001 + fpr * 0.999) if tpr + fpr else 0.0
    bench = json.loads((ROOT / "reports/triage_bench.json").read_text(encoding="utf-8"))
    return {
        "provenance": "rules (hand-set TRD weights; trained model rejected by hard checks)",
        "threshold": SETTINGS.triage_threshold,
        "recall_all_global_phishing": {"value": round(tpr, 4), "n": len(test),
                                       "dataset": "PhishTank verified + OpenPhish, temporal test third"},
        "recall_on_phishing_naming_our_40_brands": {"value": round(tpr_ours, 4) if tpr_ours is not None else None,
                                                    "n": len(ours), "missed_examples": [r["etld1"] for r in ours
                                                                                       if not triage(r["etld1"]).is_candidate][:12],
                                                    "dataset": "all positives in which triage detects one of our 40 brands "
                                                               "(token, lookalike or homoglyph)"},
        "note_global_recall": "the public feeds are dominated by brands outside our list of 40 (e.g. Bradesco, Allegro); "
                              "a brand-list triage scores those 0 by design, so global recall measures feed composition",
        "false_positive_rate": {"value": round(fpr, 6), "n": len(neg), "dataset": "Tranco 1M random sample (held out)"},
        "precision_at_1_in_1000_base_rate": {"value": round(prec, 4), "method": "TPR*0.001/(TPR*0.001+FPR*0.999)"},
        "hard_negative_fp_rate": {"value": round(hfp, 4), "n": len(hard),
                                  "dataset": "Tranco domains containing a brand token, not the brand's own"},
        "latency_us_per_name": {**bench["latency_us"], "n": bench["names_unique"],
                                "dataset": "unique names from the 30-min CT capture", "measured_at": bench["measured_at"]},
        "candidates_per_min_of_live_stream": {"value": bench["candidates_per_min_of_stream"],
                                              "dataset": "same capture"},
        "measured_at": NOW(),
    }


@section
def triage_model():
    m = json.loads((ROOT / "services/ml/artifacts/triage_metrics.json").read_text(encoding="utf-8"))
    return {"decision": m["decision"], "passed_checks": m["passed_checks"], "hard_checks": m["hard_checks"],
            "temporal": {k: m["splits"]["temporal"][k] for k in ("auc", "at_threshold", "n_test_pos", "n_test_neg")},
            "campaign_disjoint": {k: m["splits"]["campaign_disjoint"][k] for k in ("auc", "at_threshold")},
            "coefficients": m["coefficients"], "top_coefficient_share": m["top_coefficient_share"],
            "measured_at": m["trained_at"]}


# ---- ingest ------------------------------------------------------------------------------------------------
@section
def ingest():
    import redis.asyncio as aioredis

    from services.ingest.stream import run
    cap = json.loads((ROOT / "reports/ct_capture/report.json").read_text(encoding="utf-8"))

    async def bench():
        r = aioredis.from_url(SETTINGS.redis_url, db=15, decode_responses=True)  # scratch db 15, flushed after
        await r.flushdb()
        stop = asyncio.Event()
        t0 = time.perf_counter()
        task = asyncio.create_task(run("replay", r, url="", replay_file=str(ROOT / "data/capture.jsonl"), speed=0, stop=stop))
        await asyncio.sleep(20)
        n = await r.xlen("certs:raw")
        stop.set()
        await task
        el = time.perf_counter() - t0
        await r.flushdb()
        return n / el
    rate = asyncio.run(bench())
    return {"replay_unique_certs_per_sec_into_redis": {"value": round(rate, 1), "method": "20 s replay at max speed, "
                                                       "parse + fingerprint dedup + pipelined XADD, one process"},
            "live_capture": {k: cap[k] for k in ("server_entries_per_sec", "unique_certs_per_sec", "captured_per_sec",
                                                 "duplicate_delivery_share", "undelivered_share", "tiled_share_of_entries")},
            "live_outbound_load": cap["outbound"], "measured_at": NOW()}


# ---- confirmation gate on labelled local pages -------------------------------------------------------------
KIT = (ROOT / "services/api/kit_template.html").read_text(encoding="utf-8")
KIT_B = KIT.replace('<div class="container">', '<section class="container"><div>').replace(
    '  </div>\n  <div class="footer">', '  </div></section>\n  <div class="footer">')


def _pages():
    pages = {}
    for i in range(10):  # phishing, known kit A: credential POST off-site + known kit
        pages[f"pA{i}"] = ("phishing", KIT.format(brand="ICICI Bank", bg="#fff", accent="#b02a30", slug="icici",
                                                  tagline=str(i), collector=f"192.0.2.{i + 1}", ref=str(i)))
    for i in range(10):  # phishing, unknown kit B: only one strong signal available
        pages[f"pB{i}"] = ("phishing", KIT_B.format(brand="ICICI Bank", bg="#fff", accent="#000", slug="icici",
                                                    tagline=str(i), collector=f"198.51.100.{i + 1}", ref=str(i)))
    for i in range(10):  # legit look-alike: brand title + password, but posts to the brand's own domain
        pages[f"lB{i}"] = ("legit", KIT.format(brand="ICICI Bank", bg="#fff", accent="#000", slug="icici", tagline="",
                                               collector="infinity.icicibank.com", ref=str(i)))
    for i in range(10):
        pages[f"lG{i}"] = ("legit", f"<html><head><title>Blog post {i}</title></head><body><p>hello</p></body></html>")
    for i in range(5):
        pages[f"lP{i}"] = ("legit", "<html><title>This domain is for sale</title></html>")
    return pages


@section
def confirmation():
    import httpx

    from services.enrich.confirm import analyze_page
    from services.enrich.fetch import FetchedPage
    from services.enrich.fingerprint import dom_structure_hash
    from services.ingest.brands import load_brands
    pages = _pages()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = pages.get(self.path.strip("/"), ("", ""))[1].encode()
            self.send_response(200 if body else 404)
            self.send_header("content-type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    icici = next(b for b in load_brands(SETTINGS.brands_file).brands if b.name.startswith("ICICI"))
    # kit knowledge from a DISJOINT sample (not one of the evaluated pages)
    known = {dom_structure_hash(KIT.format(brand="X", bg="", accent="", slug="", tagline="", collector="x", ref="x")): "kit-A"}
    rows = []
    with httpx.Client(timeout=10) as c:
        for name, (truth, _) in pages.items():
            url = f"http://127.0.0.1:{srv.server_port}/{name}/"
            r = c.get(url)
            page = FetchedPage(url, url, r.status_code, r.text, dict(r.headers), [], None, None, [], "httpx")
            res = analyze_page(page, f"{name}.example", icici, known, {}, None, None)
            rows.append((truth, res.verdict, res.strong_count))
    srv.shutdown()
    tp = sum(t == "phishing" and v == "confirmed" for t, v, _ in rows)
    fp = sum(t == "legit" and v == "confirmed" for t, v, _ in rows)
    npos = sum(t == "phishing" for t, _, _ in rows)
    verdicts = {}
    for t, v, _ in rows:
        verdicts.setdefault(t, {}).setdefault(v, 0)
        verdicts[t][v] += 1
    return {"precision": {"value": round(tp / (tp + fp), 4) if tp + fp else None, "confirmed": tp + fp},
            "recall": {"value": round(tp / npos, 4), "n_phishing": npos},
            "false_confirmations_of_legit_pages": fp, "verdicts_by_truth": verdicts, "n": len(rows),
            "dataset": "45 labelled pages served over real HTTP from 127.0.0.1: 10 known-kit phishing, 10 unknown-kit "
                       "phishing, 10 legit brand-like logins posting to the brand, 10 blogs, 5 parked; kit knowledge "
                       "from a disjoint sample",
            "method": "real HTTP fetch + the production analyze_page gate (>= 2 strong signals)", "measured_at": NOW()}


# ---- email ---------------------------------------------------------------------------------------------------
@section
def email():
    e = json.loads((ROOT / "reports/email_eval.json").read_text(encoding="utf-8"))
    return {k: {kk: vv for kk, vv in e[k].items() if kk != "rows"} for k in ("cold", "warm")} | {
        "n_samples": e["n_samples"], "note": e["note"], "measured_at": e["measured_at"],
        "owner_decision_pending": "cold-start gate options A-D reported 2026-10-06; >=2-strong rule unchanged"}


# ---- response time (live pipeline, Supabase) ---------------------------------------------------------------
@section
def response_time(since: str | None):
    import sqlalchemy as sa

    from services.api.db import engine
    with engine().connect() as c:
        rows = c.execute(sa.text("""
            select status, extract(epoch from candidate_at - ct_seen_at) as to_candidate,
                   extract(epoch from received_at - ct_seen_at) as upstream,
                   extract(epoch from candidate_at - received_at) as ours,
                   extract(epoch from verdict_at - candidate_at) as to_verdict
            from domains where source in ('certstream','replay') and candidate_at >= coalesce(cast(:s as timestamptz), now() - interval '1 day')"""),
            {"s": since}).mappings().all()
        anchors = [r[0] for r in c.execute(sa.text(
            "select extract(epoch from anchored_at - created_at) from evidence_bundles where anchored_at is not null"))]
        plans = [r[0] for r in c.execute(sa.text("select solve_ms from interdiction_plans where backend = 'cpsat'"))]
    to_c = [float(r["to_candidate"]) for r in rows if r["to_candidate"] is not None]
    up = [float(r["upstream"]) for r in rows if r["upstream"] is not None]
    ours = [float(r["ours"]) for r in rows if r["ours"] is not None]
    to_v = [float(r["to_verdict"]) for r in rows if r["to_verdict"] is not None]
    status = {}
    for r in rows:
        status[r["status"]] = status.get(r["status"], 0) + 1
    return {"ct_seen_to_candidate_s": {"p50": pct(to_c, .5), "p95": pct(to_c, .95), "max": max(to_c) if to_c else None, "n": len(to_c)},
            "upstream_aggregator_delay_s": {"p50": pct(up, .5), "p95": pct(up, .95), "n": len(up),
                                            "what": "certstream-server-go 'seen' stamp -> our ingest receipt"},
            "our_receipt_to_candidate_s": {"p50": pct(ours, .5), "p95": pct(ours, .95), "max": max(ours) if ours else None,
                                           "n": len(ours), "what": "ingest receipt -> triage -> candidate row in Supabase"},
            "candidate_to_verdict_s": {"p50": pct(to_v, .5), "p95": pct(to_v, .95), "max": max(to_v) if to_v else None,
                                       "n": len(to_v), "target": "< 20 s (CLAUDE.md §5)"},
            "verdicts_from_live_candidates": status,
            "evidence_created_to_anchored_s": {"p50": pct(anchors, .5), "p95": pct(anchors, .95), "n": len(anchors),
                                               "note": "includes time queued while the anchor worker was not running"},
            "interdiction_cpsat_solve_ms_api": {"p50": pct(plans, .5), "max": max(plans) if plans else None, "n": len(plans)},
            "window_since": since, "dataset": "Supabase domains with source certstream/replay (seed excluded)",
            "measured_at": NOW()}


# ---- interdiction benchmark on the seeded campaign -------------------------------------------------------
@section
def interdiction():
    import sqlalchemy as sa

    from interdict.benchmark import benchmark
    from services.api.db import engine
    from services.api.routes.plans import build_problem
    with engine().connect() as c:
        cid = c.execute(sa.text("select id::text from campaigns order by domain_count desc limit 1")).scalar_one()
        base, _ = build_problem(c, cid, 4)
    out = {"campaign": cid, "domains": len(base.deps), "candidate_nodes": len(base.nodes), "by_k": {}}
    for k in (2, 3, 4, 5):
        p = type(base)(base.nodes, base.deps, base.weights, k)
        runs = [benchmark(p) for _ in range(3)]
        rows = {}
        for b in ("cpsat", "qaoa", "annealing", "greedy"):
            rr = [next(x for x in run if x.backend == b) for run in runs]
            ok = [x for x in rr if x.valid]
            rows[b] = {"domains_killed": ok[0].domains_killed if ok else None,
                       "coverage_pct": ok[0].coverage_pct if ok else None,
                       "solve_ms_median": statistics.median(x.solve_ms for x in ok) if ok else None,
                       "valid_runs": f"{len(ok)}/3", "errors": sorted({x.error for x in rr if x.error})[:2],
                       "qubits": ok[0].qubit_count if ok else None}
        out["by_k"][str(k)] = rows
    out.update(method="interdict.benchmark, 3 repetitions per k, in a standalone process, seeded campaign (synthetic, "
                      "source=seed)", measured_at=NOW())
    return out


# ---- lead time: CT certificate vs public phishing-feed listing ---------------------------------------------
@section
def lead_time():
    first_ct: dict[str, float] = {}
    with open(ROOT / "data/capture.jsonl", encoding="utf-8") as f:
        for line in f:
            m = json.loads(line)
            seen = m["data"].get("seen")
            for n in m["data"]["leaf_cert"].get("all_domains", []):
                h = n.lower().rstrip(".")
                if h.startswith("*."):
                    continue  # a wildcard does not name the phishing host (stated limit)
                if h not in first_ct or seen < first_ct[h]:
                    first_ct[h] = seen
    import io

    import httpx
    pt = httpx.get("http://data.phishtank.com/data/online-valid.csv", timeout=120, follow_redirects=True)
    pt.raise_for_status()
    from urllib.parse import urlsplit
    leads = []
    for r in csv.DictReader(io.StringIO(pt.text)):
        try:
            host = (urlsplit(r["url"]).hostname or "").lower()
            sub = datetime.fromisoformat(r["submission_time"]).timestamp()
        except (ValueError, KeyError):
            continue
        if host in first_ct:  # EXACT hostname: the phishing host's own certificate, not a platform sibling's
            leads.append((sub - first_ct[host]) / 3600)
    ahead = [x for x in leads if x > 0]
    return {"matched_domains": len(leads), "ct_first": len(ahead),
            "lead_hours": {"p50": pct(ahead, .5), "p95": pct(ahead, .95), "max": max(ahead) if ahead else None},
            "listed_before_ct_seen": len(leads) - len(ahead),
            "dataset": "our 30-min CT capture (2026-10-06 13:28-13:58 UTC) x PhishTank verified-online submission "
                       "times, matched on the EXACT hostname named in the certificate",
            "caveat": "a 30-minute window: only phishing certificates issued in that window can match; lead time is "
                      "bounded by when PhishTank was downloaded", "measured_at": NOW()}


@section
def triage_threshold_options():
    """Owner decision input (no default changed): what each rules threshold would cost and catch."""
    import json as _j

    from services.ingest.certparse import parse_message
    from services.ingest.triage import Reason, TriageResult, triage, warm  # noqa: F401
    from services.tests.test_triage import LEGIT, PHISH
    warm()
    names, seen = [], set()
    with open(ROOT / "data/capture.jsonl", encoding="utf-8") as f:
        for line in f:
            rec = parse_message(_j.loads(line))
            for n in (rec.names if rec else []):
                if n not in seen:
                    seen.add(n)
                    names.append(n)
            if len(names) >= 200_000:
                break
    span_min = json.loads((ROOT / "reports/triage_bench.json").read_text(encoding="utf-8"))["capture_span_min"]
    scores = [triage(n).score for n in names]
    hard = (ROOT / "data/ml/hard_negatives.txt").read_text(encoding="utf-8").split()
    hard_s = [triage(d).score for d in hard]
    misses = json.loads(OUT.read_text(encoding="utf-8"))["triage_rules"]["recall_on_phishing_naming_our_40_brands"]["missed_examples"]
    out = []
    for t in (0.30, 0.35, 0.40, 0.45):
        out.append({"threshold": t,
                    "candidates_per_min_live": round(sum(x >= t for x in scores) / span_min, 1),
                    "hard_negative_fp_rate": round(sum(x >= t for x in hard_s) / len(hard_s), 4),
                    "brand_phishing_caught": f"{sum(triage(d).score >= t for d in misses)}/{len(misses)}",
                    "release_gate_legit_flagged": [d for d in LEGIT if triage(d).score >= t],
                    "release_gate_phish_missed": [d for d in PHISH if triage(d).score < t]})
    return {"options": out, "n_live_names": len(names), "capture_span_min": span_min,
            "note": "rules weights unchanged; threshold remains SETTINGS.triage_threshold until the owner decides",
            "measured_at": NOW()}


@section
def evidence_ledger():
    """Re-verify real bundles from Supabase, tamper a COPY of each, and count what reached the ledger."""
    import random as _r
    import shutil
    import tempfile

    import sqlalchemy as sa

    from evidence.bundle import verify_bundle
    from services.api.db import engine
    from services.api.ledger_service import Ledger
    with engine().connect() as c:
        bundles = c.execute(sa.text("""select id::text, bundle_root, signature, collector_pk, artifact_dir
                                       from evidence_bundles""")).mappings().all()
        arts = {}
        for r in c.execute(sa.text("select bundle_id::text, name, sha256 from evidence_artifacts")).mappings():
            arts.setdefault(r["bundle_id"], {})[r["name"]] = r["sha256"]
        anchored = c.execute(sa.text("select count(*) from evidence_bundles where anchored_tx is not null")).scalar()
        published = c.execute(sa.text("select count(*) from campaigns where published_tx is not null")).scalar()
        sent = c.execute(sa.text("select count(*) from abuse_reports where sent")).scalar()
        reports = c.execute(sa.text("select count(*) from abuse_reports")).scalar()
    sample = _r.Random(3).sample(list(bundles), min(25, len(bundles)))
    ok = named = 0
    for b in sample:
        exp = arts[b["id"]]
        r = verify_bundle(Path(b["artifact_dir"]), b["bundle_root"], b["signature"], b["collector_pk"], exp)
        ok += r.valid
        with tempfile.TemporaryDirectory() as td:
            cp = Path(td) / "b"
            shutil.copytree(b["artifact_dir"], cp)
            f = cp / "dom.html"
            data = bytearray(f.read_bytes())
            data[len(data) // 2] ^= 1
            f.write_bytes(bytes(data))
            t = verify_bundle(cp, b["bundle_root"], b["signature"], b["collector_pk"], exp)
            named += (not t.valid) and [x.artifact for x in t.failures] == ["dom.html"]
    led = Ledger.from_settings(SETTINGS)
    chain_ok = led.available()
    onchain = sum(led.verify_anchor(b["id"], b["bundle_root"]) for b in sample[:10]) if chain_ok else None
    return {"bundles_reverified_valid": f"{ok}/{len(sample)}",
            "one_byte_tamper_detected_and_file_named": f"{named}/{len(sample)}",
            "bundles_total": len(bundles), "bundles_anchored_on_chain": anchored, "campaigns_published": published,
            "anchor_roots_matching_chain": f"{onchain}/10" if onchain is not None else "chain not reachable",
            "abuse_reports_generated": reports, "abuse_reports_sent": sent,
            "dataset": "Supabase evidence bundles (seeded campaign) and the local permissioned chain",
            "method": "verify_bundle on the stored files; tamper = flip one byte of dom.html in a copy",
            "measured_at": NOW()}


SECTIONS = {"evidence_ledger": evidence_ledger, "triage_threshold_options": triage_threshold_options, "triage_rules": triage_rules, "triage_model": triage_model, "ingest": ingest,
            "confirmation": confirmation, "email": email, "response_time": response_time,
            "interdiction": interdiction, "lead_time": lead_time}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since")
    ap.add_argument("--only")
    a = ap.parse_args()
    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for name, fn in SECTIONS.items():
        if a.only and name not in a.only.split(","):
            continue
        t = time.perf_counter()
        existing[name] = fn(a.since) if name == "response_time" else fn()
        print(f"{name:14} {'UNAVAILABLE' if 'unavailable' in existing[name] else 'ok'} ({time.perf_counter() - t:.0f}s)",
              flush=True)
    existing["generated_at"] = NOW()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(existing, indent=1, default=str), encoding="utf-8")
