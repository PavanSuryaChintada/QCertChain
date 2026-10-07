"""T12/T13: latency budgets (server-side p95) and one data query per endpoint, measured against the SEEDED datasets
of BOTH organisations (org 1: 400 domains, org 2: 50 on overlapping infrastructure), so the org-scoping filters
are in the measured path. A budget miss fails with EXPLAIN ANALYZE of the statements that request ran.

Where budgets are enforced: they assume a co-located database (T11: API and database both in Singapore, round
trip ~1 ms). The query-count rule is enforced everywhere. The latency budgets are enforced in CI (env CI set;
GitHub Actions with a local Postgres service) and wherever the measured database round trip is co-located
(p95 <= 5 ms). On a contended developer machine (measured here: Docker Desktop on Windows, round trip p95 ~30 ms,
CPU at 100 %) the numbers are recorded in reports/api_latency.json and the budget check is reported as not
enforced, rather than adjusted.
"""
import json

import pytest
import sqlalchemy as sa

from services.api import timing

BUDGET_MS = {"list": 150, "graph": 300, "solve": 500, "verify": 400}
RUNS = 30
COLOCATED_RTT_MS = 5.0
SCOPE_STMTS = ("select set_config(", "reset role")  # binding the org; not data queries


@pytest.fixture
def world(api):
    from services.api.main import app
    app.state.warmup.join(timeout=120)  # OR-Tools load + QAOA worker spawn must not be inside the measurement
    admin = api.as_("admin")
    o1 = api.post("/admin/seed", headers=admin, json={"label": "lat-org1", "domains": 400, "org": "org1"}).json()
    o2 = api.post("/admin/seed", headers=admin, json={
        "label": "lat-org2", "domains": 50, "ips": 6, "asns": 2, "nameservers": 3, "brands": ["HDFC Bank"],
        "org": "org2", "ip_base": 100, "shared_ips": ["198.51.100.10"],
        "shared_nameservers": ["ns1.lat-org1-dns.example"]}).json()
    out = {}
    for org, camp in (("org1", o1["campaign_id"]), ("org2", o2["campaign_id"])):
        h = api.as_(org)
        g = api.get(f"/campaigns/{camp}/graph", headers=h).json()
        bid = api.get(f"/domains/{g['domains'][0][0]}", headers=h).json()["evidence_bundle_id"]
        out[org] = {"campaign": camp, "domain": g["domains"][0][0], "bundle": bid}
    return out


def endpoints(w, org):
    x = w[org]
    return [("list", "GET", "/campaigns", None), ("list", "GET", "/candidates", None),
            ("list", "GET", "/email/analyses", None), ("list", "GET", f"/domains/{x['domain']}", None),
            ("graph", "GET", f"/campaigns/{x['campaign']}/graph", None),
            ("graph", "GET", f"/campaigns/{x['campaign']}/sweep", None),
            ("solve", "POST", f"/campaigns/{x['campaign']}/interdict", {"k": 5, "backend": "cpsat"}),
            ("verify", "GET", f"/evidence/{x['bundle']}/verify", None)]


def _rtt_p95(db) -> float:
    import time
    xs = []
    for _ in range(200):
        t = time.perf_counter()
        db.execute(sa.text("select 1")).scalar()
        xs.append((time.perf_counter() - t) * 1000)
    xs.sort()
    return xs[int(0.95 * (len(xs) - 1))]


def _capture(db):
    stmts = []

    def on(conn, cursor, statement, params, context, executemany):
        stmts.append((statement, params))
    sa.event.listen(db, "before_cursor_execute", on)
    return stmts, lambda: sa.event.remove(db, "before_cursor_execute", on)


def _explain(db, org_id, stmts) -> str:
    out = []
    for stmt, params in stmts:
        low = stmt.lstrip().lower()
        if low.startswith(SCOPE_STMTS) or not low.startswith(("select", "with")):
            continue
        sp = db.begin_nested()
        try:
            db.exec_driver_sql("select set_config('app.org_id', %(o)s, true), set_config('role', 'qcc_app', true)",
                               {"o": str(org_id)})
            plan = db.exec_driver_sql("explain (analyze, buffers) " + stmt, params).scalars().all()
            out.append(stmt.strip()[:300] + "\n" + "\n".join(plan))
        finally:
            sp.rollback()
    return "\n\n".join(out)


@pytest.mark.db
@pytest.mark.perf
def test_latency_budgets_and_one_data_query_per_endpoint(api, db, world):
    report = {}
    failures = []
    import os
    rtt = _rtt_p95(db)
    enforce = bool(os.environ.get("CI")) or rtt <= COLOCATED_RTT_MS
    report["environment"] = {"db_round_trip_p95_ms": round(rtt, 1), "ci": bool(os.environ.get("CI")),
                             "budgets_enforced": enforce}
    for org, org_id in (("org1", 1), ("org2", 2)):
        h = api.as_(org)
        for kind, method, path, body in endpoints(world, org):
            api.request(method, path, headers=h, json=body)  # warm (also fills a lazily built sweep once)
            timing.reset()
            stmts, stop = _capture(db)
            try:
                for _ in range(RUNS):
                    stmts.clear()
                    r = api.request(method, path, headers=h, json=body)
                    assert r.status_code == 200, (org, path, r.status_code, r.text[:200])
            finally:
                stop()
            data = [s for s, _ in stmts if not s.lstrip().lower().startswith(SCOPE_STMTS)]
            p95 = max(v["p95_ms"] for v in timing.summary().values())
            report[f"{org} {method} {path.split('/')[1]}{'/' + path.rsplit('/', 1)[-1] if path.count('/') > 2 else ''}"] = \
                {"p95_ms": p95, "budget_ms": BUDGET_MS[kind], "within_budget": p95 <= BUDGET_MS[kind],
                 "data_queries": len(data)}
            max_q = 2 if kind == "solve" else 1  # interdiction: one read of the snapshot + one write (plan, targets, log)
            if len(data) > max_q:
                failures.append(f"{org} {method} {path}: {len(data)} data queries (max {max_q}):\n  " +
                                "\n  ".join(" ".join(s.split())[:140] for s in data))
            if enforce and p95 > BUDGET_MS[kind]:
                failures.append(f"{org} {method} {path}: p95 {p95} ms > {BUDGET_MS[kind]} ms budget\n" +
                                _explain(db, org_id, stmts))
    print(json.dumps(report, indent=1))
    from pathlib import Path
    Path("reports").mkdir(exist_ok=True)
    Path("reports/api_latency.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    assert not failures, "\n\n".join(failures)
    if not enforce:
        import warnings
        warnings.warn(f"latency budgets NOT enforced: database round trip p95 {rtt:.1f} ms (not co-located, not CI); "
                      "measurements recorded in reports/api_latency.json")
