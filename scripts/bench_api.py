"""Endpoint latency + query count against the SEEDED datasets of BOTH orgs (org-scoping filters in the measured
path). Runs in-process (TestClient) against the local test database, so it measures the API and its queries,
not a network hop. Usage: python -m scripts.bench_api [--runs 30] [--json reports/api_latency.json]
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from contextlib import contextmanager
from pathlib import Path

import sqlalchemy as sa

ORG1_IP, ORG1_NS = "198.51.100.10", "ns1.bench-org1-dns.example"


def p95(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]


@contextmanager
def seeded_client(url: str, tmp: Path):
    """Fresh schema, both orgs seeded through the admin API, keys for each org. Yields (client, ids, conn)."""
    import fakeredis
    import fakeredis.aioredis
    import nacl.signing
    from fastapi.testclient import TestClient

    from scripts.apply_schema import apply
    from services.api import auth, deps, main
    from services.api.db import unbind_org

    eng = sa.create_engine(url)
    with eng.begin() as c:
        c.exec_driver_sql("drop schema public cascade; create schema public;")
    apply(url)
    conn = eng.connect()
    conn.begin()
    keys = {k: auth.create_key(conn, kind, org) for k, kind, org in
            (("org1", "org", "org1"), ("org2", "org", "org2"), ("admin", "admin", None))}
    server = fakeredis.FakeServer()
    sk = nacl.signing.SigningKey.generate().encode().hex()

    def get_conn():
        try:
            yield conn
        finally:  # one shared transaction: undo the request's org scope (a real request's transaction ends)
            if conn.in_transaction():
                unbind_org(conn)

    main.app.dependency_overrides[deps.get_conn] = get_conn
    main.app.dependency_overrides[deps.get_redis] = lambda: fakeredis.aioredis.FakeRedis(server=server,
                                                                                         decode_responses=True)
    main.app.dependency_overrides[deps.get_evidence_dir] = lambda: tmp
    main.app.dependency_overrides[deps.get_signing_key] = lambda: sk
    try:
        with TestClient(main.app) as cl:
            admin = {auth.HEADER: keys["admin"]}
            o1 = cl.post("/admin/seed", headers=admin, json={"label": "bench-org1", "domains": 400, "org": "org1"}).json()
            o2 = cl.post("/admin/seed", headers=admin, json={
                "label": "bench-org2", "domains": 50, "ips": 6, "asns": 2, "nameservers": 3, "brands": ["HDFC Bank"],
                "org": "org2", "ip_base": 100, "shared_ips": [ORG1_IP], "shared_nameservers": [ORG1_NS]}).json()
            yield cl, keys, {"org1": o1["campaign_id"], "org2": o2["campaign_id"]}, conn
    finally:
        main.app.dependency_overrides.clear()
        conn.rollback()
        conn.close()
        eng.dispose()


def endpoints(cl, keys, camps) -> dict[str, list[tuple[str, str, dict | None, str]]]:
    """name -> [(method, path, body, org)] for both orgs."""
    out: dict[str, list] = {}
    for org in ("org1", "org2"):
        h = keys[org]
        cid = camps[org]
        g = cl.get(f"/campaigns/{cid}/graph", headers={"X-API-Key": h}).json()
        did = g["domains"][0][0]
        bid = cl.get(f"/domains/{did}", headers={"X-API-Key": h}).json()["evidence_bundle_id"]
        for name, method, path, body in (
                ("list campaigns", "GET", "/campaigns", None),
                ("list candidates", "GET", "/candidates?limit=50", None),
                ("list email analyses", "GET", "/email/analyses", None),
                ("domain detail", "GET", f"/domains/{did}", None),
                ("campaign graph", "GET", f"/campaigns/{cid}/graph", None),
                ("campaign sweep", "GET", f"/campaigns/{cid}/sweep", None),
                ("interdiction solve", "POST", f"/campaigns/{cid}/interdict", {"k": 5, "backend": "cpsat"}),
                ("evidence verify", "GET", f"/evidence/{bid}/verify", None)):
            out.setdefault(name, []).append((method, path, body, org))
    return out


def measure(cl, keys, eps, runs: int, conn) -> dict:
    from services.api import timing
    count = {"n": 0}

    def on_exec(*_a, **_k):
        count["n"] += 1
    sa.event.listen(conn, "before_cursor_execute", on_exec)
    res = {}
    try:
        for name, calls in eps.items():
            times, queries = [], []
            timing.reset()
            for method, path, body, org in calls:
                h = {"X-API-Key": keys[org]}
                cl.request(method, path, headers=h, json=body)  # warm
                for _ in range(runs):
                    count["n"] = 0
                    t = time.perf_counter()
                    r = cl.request(method, path, headers=h, json=body)
                    times.append((time.perf_counter() - t) * 1000)
                    queries.append(count["n"])
                    assert r.status_code == 200, (name, org, r.status_code, r.text[:200])
            server = [v for v in timing.summary().values()]
            srv = max(server, key=lambda v: v["count"]) if server else {}
            res[name] = {"server_p50_ms": srv.get("p50_ms"), "server_p95_ms": srv.get("p95_ms"),
                         "client_p95_ms": round(p95(times), 1), "queries_per_request": max(queries),
                         "samples": len(times)}
    finally:
        sa.event.remove(conn, "before_cursor_execute", on_exec)
    return res


def main() -> None:
    import tempfile
    import multiprocessing  # noqa: F401  (QAOA worker spawn needs a real __main__)

    from services.config import SETTINGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--json")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp, seeded_client(SETTINGS.test_database_url, Path(tmp)) as (cl, keys, camps, conn):
        time.sleep(8)  # lifespan warm-up (OR-Tools, QAOA worker) must not be inside the measurement
        res = measure(cl, keys, endpoints(cl, keys, camps), a.runs, conn)
        g = cl.get(f"/campaigns/{camps['org1']}/graph", headers={"X-API-Key": keys["org1"]})
        res["campaign graph"]["payload_kb_400_domains"] = round(len(g.content) / 1024, 1)
    for k, v in res.items():
        print(f"{k:22s} {v}")
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
