"""Assemble triage training data (MODELS.md §2, §8) and REPORT COUNTS before any training.

Positives: PhishTank verified-online (submission time, last 90 days) + OpenPhish public feed (no timestamps;
stamped with fetch time). Negatives: Tranco top-1M random sample. Hard negatives: Tranco domains containing a
brand token that are not the brand's own domains and not in the phishing set — "this set matters most".

Stop rule (MODELS.md §8): fewer than 5,000 positives after de-duplication by campaign -> do not train; ship the
hand-set rule weights with provenance "rules". Fewer than 200 hard negatives -> tell the owner.
"""
from __future__ import annotations

import csv
import io
import json
import random
import re
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx

from services.config import ROOT, SETTINGS
from services.ingest.brands import etld1, load_brands

OUT = ROOT / "data/ml"
PHISHTANK = "http://data.phishtank.com/data/online-valid.csv"
OPENPHISH = "https://openphish.com/feed.txt"
TRANCO = "https://tranco-list.eu/top-1m.csv.zip"
MIN_POSITIVES, MIN_HARD_NEGATIVES = 5000, 200


def campaign_key(name: str) -> str:
    """Same-campaign names differ by numbers: sbi-verify-01.top ~ sbi-verify-400.top."""
    return re.sub(r"\d+", "#", name.lower())


def dedupe_by_campaign(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["seen"]):
        k = campaign_key(r["etld1"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _host_etld1(url: str) -> str | None:
    try:
        h = urlsplit(url.strip()).hostname
    except ValueError:
        return None
    return etld1(h.lower()) if h and "." in h else None


def fetch_positives(now: datetime) -> tuple[list[dict], dict]:
    meta, rows = {}, []
    with httpx.Client(timeout=120, follow_redirects=True, headers={"User-Agent": SETTINGS.user_agent}) as c:
        pt = c.get(PHISHTANK)
        pt.raise_for_status()
        cutoff = now - timedelta(days=90)
        n_pt = 0
        for r in csv.DictReader(io.StringIO(pt.text)):
            try:
                seen = datetime.fromisoformat(r["submission_time"])
            except (KeyError, ValueError):
                continue
            d = _host_etld1(r.get("url", ""))
            if d and seen >= cutoff:
                rows.append({"etld1": d, "seen": seen, "source": "phishtank", "target": r.get("target") or ""})
                n_pt += 1
        op = c.get(OPENPHISH)
        op.raise_for_status()
        n_op = 0
        for line in op.text.splitlines():
            d = _host_etld1(line)
            if d:
                rows.append({"etld1": d, "seen": now, "source": "openphish", "target": ""})
                n_op += 1
    meta.update(phishtank_rows_last_90d=n_pt, openphish_rows=n_op, fetched_at=now.isoformat())
    return rows, meta


def fetch_tranco() -> list[str]:
    r = httpx.get(TRANCO, timeout=180, follow_redirects=True)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        lines = z.read(z.namelist()[0]).decode("utf-8").splitlines()
    return [ln.split(",", 1)[1].strip().lower() for ln in lines if "," in ln]


def hard_negatives(tranco: list[str], phish: set[str]) -> list[str]:
    idx = load_brands(SETTINGS.brands_file)
    long_tokens = [t for t in idx.by_token if len(t) > 3]
    short = {t for t in idx.by_token if len(t) <= 3}
    out = []
    for d in tranco:
        e = etld1(d)
        if not e or e in idx.legit_etld1s or e in phish:
            continue
        label = e.split(".")[0]
        if any(t in label for t in long_tokens) or short & set(re.split(r"[-.0-9]+", label)):
            out.append(e)
    return sorted(set(out))


def main() -> int:
    now = datetime.now(timezone.utc)
    OUT.mkdir(parents=True, exist_ok=True)
    pos, meta = fetch_positives(now)
    by_domain = {}
    for r in pos:
        by_domain.setdefault(r["etld1"], r)
    unique = list(by_domain.values())
    deduped = dedupe_by_campaign(unique)
    tranco = fetch_tranco()
    phish_set = set(by_domain)
    hard = hard_negatives(tranco, phish_set)
    rng = random.Random(42)
    negatives = rng.sample([d for d in tranco if d not in phish_set], min(200_000, len(tranco)))
    idx = load_brands(SETTINGS.brands_file)
    on_our_brands = sum(1 for r in deduped if any(t in r["etld1"] for t in idx.by_token if len(t) > 3))
    counts = {**meta, "positives_unique_etld1": len(unique), "positives_after_campaign_dedup": len(deduped),
              "positives_matching_our_40_brands": on_our_brands, "negatives_sampled": len(negatives),
              "hard_negatives": len(hard), "tranco_rows": len(tranco),
              "train": len(deduped) >= MIN_POSITIVES,
              "decision": ("train" if len(deduped) >= MIN_POSITIVES else
                           f"STOP: {len(deduped)} < {MIN_POSITIVES} positives after campaign dedup — ship hand-set "
                           "rule weights with provenance 'rules' (MODELS.md §8)")}
    with open(OUT / "positives.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["etld1", "seen", "source", "target"])
        w.writeheader()
        for r in deduped:
            w.writerow({**r, "seen": r["seen"].isoformat()})
    (OUT / "hard_negatives.txt").write_text("\n".join(hard) + "\n", encoding="utf-8")
    (OUT / "negatives.txt").write_text("\n".join(negatives) + "\n", encoding="utf-8")
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/ml_dataset_counts.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    print(json.dumps(counts, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
