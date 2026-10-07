"""Record a long live-CT window (item 7) for three uses, from one connection to the self-hosted certstream:

1. A REPLAY FIXTURE (gzip JSONL, the same message format the ingest replays): every certificate with a name that
   triages >= --keep-score (default 0.20), plus a labelled --sample fraction (default 1 %) of the rest so the stream
   rail still scrolls. 24 h of CT is ~260 M certificates; nothing plays that back in minutes, so the fixture keeps
   what the demo can show and says what it dropped. Messages keep their real `seen` time: replay at speed S plays
   24 h in 24 h / S (S = 360 -> 4 min).
2. A FIRST-SEEN INDEX (SQLite) of every non-allowlisted name: when CT first showed it.
3. OPENPHISH LISTINGS polled every 30 min (the public feed; one request per poll): when each URL was first listed.
   Together, 2 and 3 MEASURE lead time = listed_at - ct_first_seen for hosts that appeared in CT first.

    python -m scripts.record_ct --hours 24 --out data/replay/ct_live.jsonl.gz --db data/replay/ct_live.sqlite
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import random
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import websockets

from services.config import SETTINGS
from services.ingest.certparse import parse_message
from services.ingest.triage import triage, warm

OPENPHISH = "https://openphish.com/feed.txt"


def _db(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.execute("pragma journal_mode=wal")
    c.execute("pragma synchronous=normal")
    c.execute("create table if not exists ct_first_seen (name text primary key, first_seen real not null, score real)")
    c.execute("create table if not exists openphish (url text primary key, host text not null, first_listed real not null)")
    c.execute("create index if not exists openphish_host on openphish (host)")
    return c


async def poll_openphish(db: sqlite3.Connection, stop: asyncio.Event, every_s: int) -> None:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True, headers={"User-Agent": SETTINGS.user_agent}) as client:
        while not stop.is_set():
            try:
                r = await client.get(OPENPHISH)
                r.raise_for_status()
                now = time.time()
                rows = [(u, (urlsplit(u).hostname or "").lower().rstrip("."), now)
                        for u in r.text.split() if u.startswith("http")]
                db.executemany("insert or ignore into openphish values (?, ?, ?)", rows)
                db.commit()
                print(f"[{datetime.now(timezone.utc):%H:%M}] openphish: {len(rows)} urls in feed", flush=True)
            except Exception as e:  # a failed poll is logged and retried at the next interval
                print(f"openphish poll failed: {type(e).__name__}: {e}", flush=True)
            try:
                await asyncio.wait_for(stop.wait(), every_s)
            except asyncio.TimeoutError:
                pass


async def record(a: argparse.Namespace) -> dict:
    warm()
    out, dbp = Path(a.out), Path(a.db)
    out.parent.mkdir(parents=True, exist_ok=True)
    db = _db(dbp)
    rng = random.Random(7)
    stop = asyncio.Event()
    end = time.monotonic() + a.hours * 3600
    stats = {"certs": 0, "names": 0, "kept_scored": 0, "kept_sample": 0, "candidates_at_0_35": 0,
             "indexed_names": 0, "started": datetime.now(timezone.utc).isoformat()}
    pending: list[tuple] = []
    last_flush = time.monotonic()
    poller = asyncio.create_task(poll_openphish(db, stop, a.openphish_every_s))
    with gzip.open(out, "at", encoding="utf-8", compresslevel=6) as f:
        while time.monotonic() < end:
            try:
                async with websockets.connect(SETTINGS.certstream_url, max_size=2**24, open_timeout=20) as ws:
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        rec = parse_message(msg)
                        if not rec or not rec.names:
                            continue
                        stats["certs"] += 1
                        best = 0.0
                        seen = msg.get("data", {}).get("seen") or time.time()
                        for n in rec.names:
                            stats["names"] += 1
                            t = triage(n, issuer=rec.issuer, san_count=rec.san_count)
                            best = max(best, t.score)
                            if not any(x.feature == "allowlisted" for x in t.reasons):
                                pending.append((n.lower().rstrip("."), seen, t.score))
                        if best >= 0.35:
                            stats["candidates_at_0_35"] += 1
                        if best >= a.keep_score:
                            msg["qcertchain_fixture"] = "scored"
                            f.write(json.dumps(msg, separators=(",", ":")) + "\n")
                            stats["kept_scored"] += 1
                        elif rng.random() < a.sample:
                            msg["qcertchain_fixture"] = "background_sample"
                            f.write(json.dumps(msg, separators=(",", ":")) + "\n")
                            stats["kept_sample"] += 1
                        if time.monotonic() - last_flush > 5:
                            db.executemany("insert or ignore into ct_first_seen values (?, ?, ?)", pending)
                            db.commit()
                            stats["indexed_names"] += len(pending)
                            pending.clear()
                            last_flush = time.monotonic()
                            f.flush()
                        if stats["certs"] % 200_000 == 0:
                            print(f"[{datetime.now(timezone.utc):%H:%M}] {stats}", flush=True)
                        if time.monotonic() >= end:
                            break
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as e:
                print(f"reconnecting after {type(e).__name__}", flush=True)
                await asyncio.sleep(5)
    if pending:
        db.executemany("insert or ignore into ct_first_seen values (?, ?, ?)", pending)
        db.commit()
    stop.set()
    await poller
    stats["finished"] = datetime.now(timezone.utc).isoformat()
    stats["fixture"] = str(out)
    stats["keep_score"], stats["sample"] = a.keep_score, a.sample
    Path(str(out) + ".summary.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--out", default="data/replay/ct_live.jsonl.gz")
    ap.add_argument("--db", default="data/replay/ct_live.sqlite")
    ap.add_argument("--keep-score", type=float, default=0.20)
    ap.add_argument("--sample", type=float, default=0.01)
    ap.add_argument("--openphish-every-s", type=int, default=1800)
    print(json.dumps(asyncio.run(record(ap.parse_args())), indent=1))


if __name__ == "__main__":
    main()
