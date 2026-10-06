"""Triage over real captured names: latency percentiles + candidate volume. Writes reports/triage_bench.json."""
import argparse
import json
import random
import time
from collections import Counter
from datetime import datetime, timezone

from services.config import ROOT, SETTINGS
from services.ingest.certparse import parse_message
from services.ingest.triage import triage, warm

ap = argparse.ArgumentParser()
ap.add_argument("--names", type=int, default=200_000)
ap.add_argument("--capture", default=SETTINGS.replay_file)
a = ap.parse_args()

names, issuers, seen_ts, uniq = [], [], [], set()
with open(ROOT / a.capture, encoding="utf-8") as f:
    for line in f:
        rec = parse_message(json.loads(line))
        if rec:
            seen_ts.append(rec.seen_at.timestamp())
            for n in rec.names:
                if n in uniq:  # same name re-issued / seen in several logs: triaged once downstream too
                    continue
                uniq.add(n)
                names.append(n)
                issuers.append(rec.issuer)
        if len(names) >= a.names:
            break
span_min = (max(seen_ts) - min(seen_ts)) / 60 if seen_ts else 0
warm()
lat, cands = [], []
for n, iss in zip(names, issuers):
    t = time.perf_counter()
    r = triage(n, issuer=iss)
    lat.append(time.perf_counter() - t)
    if r.is_candidate:
        cands.append((n, r.score, r.brand, [x.feature for x in r.reasons]))
lat.sort()
pct = lambda q: lat[int(q * (len(lat) - 1))] * 1e6
out = {
    "measured_at": datetime.now(timezone.utc).isoformat(), "capture": a.capture, "names_unique": len(names),
    "capture_span_min": round(span_min, 2),
    "latency_us": {"p50": round(pct(0.5), 1), "p95": round(pct(0.95), 1), "p99": round(pct(0.99), 1), "max": round(lat[-1] * 1e6, 1)},
    "candidates": len(cands),
    "candidates_per_min_of_stream": round(len(cands) / span_min, 1) if span_min else None,
    "by_brand": Counter(c[2] for c in cands).most_common(15),
    "sample": random.Random(0).sample(cands, min(40, len(cands))),
}
(ROOT / "reports").mkdir(exist_ok=True)
(ROOT / "reports/triage_bench.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k != "sample"}, indent=1, ensure_ascii=False))
