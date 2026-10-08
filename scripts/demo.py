"""Demo-day tooling: make every page fast before the audience sees it, and know the stack is ready.

    PYTHONPATH=. python -m scripts.demo reset      reset demo data (admin), publish Bank One's campaign, wait for the
                                                   anchors, then warm
    PYTHONPATH=. python -m scripts.demo warm       pre-compute everything a page could be cold on (exit 1 on any non-200)
    PYTHONPATH=. python -m scripts.demo check      one readiness table: API, database, chain + anchors, stream, both
                                                   orgs' campaigns, console, worker backlog (exit 1 if not ready)
    PYTHONPATH=. python -m scripts.demo console    build the console for production and serve it on :5180 (faster than
                                                   the dev server; same URL)
    PYTHONPATH=. python -m scripts.demo flush      drop the stale page-fetch backlog right before presenting (the
                                                   domains stay candidates); keeps the enrich status "ok" while live

Keys come from .env (QCC_KEY_ORG1, QCC_KEY_ORG2, QCC_KEY_ADMIN). Options: --api URL (default http://127.0.0.1:8000),
--console URL (default http://localhost:5180).

Why warm: after a reset the solver benchmark for a k is computed on first request (seconds, ~30 s cold for all five
solvers), evidence verification reads files and the chain, and every response pays Supabase round trips. Warming
once makes each of those a cache hit while presenting. The benchmark is warmed with run=false (the cached-result
path the page loads); "Run again" on camera stays a genuine live run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWEEP_KS = range(1, 16)  # fallback only; the sweep's own k values are used


def env_keys(path: Path = ROOT / ".env") -> dict[str, str]:
    """QCC_KEY_* values from .env (never printed)."""
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("QCC_KEY_") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def largest(items: list[dict]) -> dict | None:
    return max(items, key=lambda c: c.get("domain_count", 0), default=None)


class Api:
    def __init__(self, base: str, key: str | None):
        self.base, self.key = base.rstrip("/"), key
        self.log: list[tuple[str, int, float]] = []

    def call(self, path: str, method: str = "GET", timeout: float = 600) -> tuple[int, object]:
        req = urllib.request.Request(self.base + path, method=method,
                                     headers={"X-API-Key": self.key} if self.key else {})
        t = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status, body = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            status, body = 0, str(e).encode()
        self.log.append((f"{method} {path}", status, (time.perf_counter() - t) * 1000))
        try:
            return status, json.loads(body or b"null")
        except ValueError:
            return status, body.decode("utf-8", "replace")[:200]


def warm(base: str, keys: dict[str, str]) -> list[tuple[str, int, float]]:
    """Every read the DEMO.md path makes, for both organisations. Returns (call, status, ms) rows."""
    rows = []
    o1, o2 = Api(base, keys.get("QCC_KEY_ORG1")), Api(base, keys.get("QCC_KEY_ORG2"))
    kit = None
    for api in (o1, o2):
        for p in ("/status", "/stream/state", "/candidates?limit=200", "/candidates/counts", "/scaling",
                  "/metrics", "/metrics/report", "/ledger/status", "/ledger/events?limit=100",
                  "/email/analyses?limit=50", "/ops/log?limit=100"):
            api.call(p)
        st, page = api.call("/campaigns?limit=200")
        c = largest(page.get("items", [])) if st == 200 and isinstance(page, dict) else None
        if c:
            cid = c["id"]
            for p in (f"/campaigns/{cid}", f"/campaigns/{cid}/graph"):
                api.call(p)
            st, sw = api.call(f"/campaigns/{cid}/sweep")
            # exactly the k values the page's slider offers (the sweep), never beyond the campaign's targets
            ks = [pt["k"] for pt in sw.get("points", [])] if st == 200 and isinstance(sw, dict) else list(SWEEP_KS)
            for k in ks:
                api.call(f"/campaigns/{cid}/benchmark?k={k}&run=false")
            st, camp = api.call(f"/campaigns/{cid}")
            if api is o1 and st == 200 and isinstance(camp, dict):
                kit = camp.get("kit_hash")
            st, g = api.call(f"/campaigns/{cid}/graph")
            if st == 200 and isinstance(g, dict) and g.get("domains"):
                st, d = api.call(f"/domains/{g['domains'][0][0]}")
                bid = d.get("evidence_bundle_id") if st == 200 and isinstance(d, dict) else None
                if bid:
                    for p in (f"/evidence/{bid}", f"/evidence/{bid}/verify", f"/evidence/{bid}/report"):
                        api.call(p)
    if kit:
        o2.call(f"/ledger/by-kit/{kit}")  # the consortium step: Bank Two finds Bank One's report
    for api in (o1, o2):
        rows += api.log
    return rows


def failures(rows: list[tuple[str, int, float]]) -> list[tuple[str, int, float]]:
    return [r for r in rows if r[1] != 200]


def readiness(base: str, console: str, keys: dict[str, str]) -> list[tuple[str, bool, str]]:
    """(check, ok, detail) rows. Every row must be ok before presenting."""
    out = []
    a1, a2, adm = Api(base, keys.get("QCC_KEY_ORG1")), Api(base, keys.get("QCC_KEY_ORG2")), Api(base, None)
    st, h = adm.call("/health", timeout=30)
    out.append(("API /health", st == 200, f"HTTP {st}" + (f", database round trip {h.get('database_round_trip_ms')} ms"
                                                          if isinstance(h, dict) else "")))
    st, s = a1.call("/status", timeout=60)
    s = s if isinstance(s, dict) else {}
    led, stream = s.get("ledger", {}), s.get("stream", {})
    out.append(("ledger (local chain)", st == 200 and bool(led.get("available")),
                f"available={led.get('available')}, anchor queue {led.get('queue_depth')}"))
    out.append(("CT stream", st == 200 and stream.get("connection") in ("connected", "replay"),
                f"mode {stream.get('mode')}, {stream.get('connection')}, {stream.get('certs_per_sec')} certs/s"))
    backlog = (stream.get("queue_depth") or {}).get("enrich")
    out.append(("enrich backlog", backlog is not None and backlog < 500,
                f"{backlog} queued; run `scripts.demo flush` right before presenting if this is over 500"))
    for label, api, size in (("Bank One campaign", a1, 470), ("Bank Two campaign", a2, 50)):
        st, page = api.call("/campaigns?limit=200", timeout=60)
        c = largest(page.get("items", [])) if st == 200 and isinstance(page, dict) else None
        ok = bool(c) and c.get("domain_count") == size and (label == "Bank Two campaign" or bool(c.get("anchored")))
        out.append((label, ok, f"{c.get('domain_count')} domains, anchored={c.get('anchored')}" if c else f"HTTP {st}"))
    try:
        with urllib.request.urlopen(console, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
        out.append(("console", r.status == 200 and 'id="root"' in html, f"{console} HTTP {r.status}"))
    except Exception as e:  # noqa: BLE001 - reported, not raised
        out.append(("console", False, f"{console}: {type(e).__name__}"))
    return out


async def flush_backlog(r) -> dict[str, int]:
    """Drop the pending page-fetch backlog (enrich:queue) and its scheduled re-checks (enrich:retry). The domains stay
    candidates; nothing in the database changes. On one laptop the fetcher (~240/h) cannot keep up with the live feed
    (~600 candidates/h), so the backlog only grows; flushed right before presenting, the running worker keeps it under
    the "ok" line (500) for over an hour."""
    from services.api.workers.enrich_worker import QUEUE, RETRY_ZSET
    out = {"queued": await r.llen(QUEUE), "scheduled_rechecks": await r.zcard(RETRY_ZSET)}
    await r.delete(QUEUE, RETRY_ZSET)
    return out


def flush() -> int:
    import asyncio

    import redis.asyncio as aioredis

    from services.config import SETTINGS

    async def go():
        r = aioredis.from_url(SETTINGS.redis_url, decode_responses=True)
        try:
            return await flush_backlog(r)
        finally:
            await r.aclose()
    out = asyncio.run(go())
    print(f"dropped {out['queued']} pending fetches and {out['scheduled_rechecks']} scheduled re-checks; "
          "those domains stay candidates. Keep the enrich worker running.")
    return 0


def reset(base: str, keys: dict[str, str]) -> int:
    adm, o1 = Api(base, keys.get("QCC_KEY_ADMIN")), Api(base, keys.get("QCC_KEY_ORG1"))
    st, r = adm.call("/admin/reset", method="POST", timeout=1800)
    if st != 200:
        print(f"reset failed: HTTP {st} {r}")
        return 1
    cid = r["seeded"]["org1"]["campaign_id"]
    print(f"reset: {json.dumps(r['seeded'])}")
    st, r = o1.call(f"/ledger/publish/{cid}", method="POST", timeout=120)
    print(f"publish Bank One's campaign: HTTP {st}")
    end = time.monotonic() + 1200
    while time.monotonic() < end:
        st, c = o1.call(f"/campaigns/{cid}", timeout=60)
        if st == 200 and isinstance(c, dict) and c.get("anchored"):
            print("anchored on the local chain")
            break
        time.sleep(10)
    else:
        print("not anchored within 20 min: is the anchor worker running and the chain up?")
        return 1
    return run_warm(base, keys)


def run_warm(base: str, keys: dict[str, str]) -> int:
    t = time.perf_counter()
    rows = warm(base, keys)
    bad = failures(rows)
    slow = sorted(rows, key=lambda r: -r[2])[:5]
    print(f"warmed {len(rows)} calls in {time.perf_counter() - t:.0f} s; slowest: "
          + ", ".join(f"{c} {ms:.0f} ms" for c, _, ms in slow))
    for c, st, ms in bad:
        print(f"  FAILED {c}: HTTP {st}")
    return 1 if bad else 0


def serve_console(api: str, port: int) -> int:
    import os
    import shutil
    import subprocess
    console = ROOT / "apps" / "console"
    npm = shutil.which("npm") or "npm"
    print("building the console for production ...", flush=True)
    b = subprocess.run(f'"{npm}" run build', cwd=console, shell=True, env={**os.environ, "VITE_API_URL": api})
    if b.returncode:
        return b.returncode
    from scripts.e2e_stack import serve
    print(f"serving {console / 'dist'} on http://localhost:{port}", flush=True)
    serve(str(console / "dist"), port)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["reset", "warm", "check", "console", "flush"])
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--console", default="http://localhost:5180")
    ap.add_argument("--port", type=int, default=5180)
    a = ap.parse_args()
    keys = env_keys()
    if a.command == "console":
        return serve_console(a.api, a.port)  # 127.0.0.1: no IPv6-first penalty per connection
    if a.command == "reset":
        return reset(a.api, keys)
    if a.command == "flush":
        return flush()
    if a.command == "warm":
        return run_warm(a.api, keys)
    rows = readiness(a.api, a.console, keys)
    width = max(len(r[0]) for r in rows)
    for name, ok, detail in rows:
        print(f"  {'OK  ' if ok else 'FAIL'}  {name:<{width}}  {detail}")
    ready = all(ok for _, ok, _ in rows)
    print("READY" if ready else "NOT READY")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
