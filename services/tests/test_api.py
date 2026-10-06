import asyncio
import json
from pathlib import Path

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.db
PROBLEM = "application/problem+json"


def test_health(api):
    assert api.get("/health").json()["status"] == "ok"


def test_seed_returns_labelled_campaign(api, seeded):
    c = api.get(f"/campaigns/{seeded}").json()
    assert c["domain_count"] == 60 and c["label"].startswith("CAMP-")
    items = api.get("/candidates?status=confirmed&limit=5").json()["items"]
    assert items and all(i["source"] == "seed" for i in items)


def test_interdict_plan_shape_and_honest_counts(api, seeded):
    plan = api.post(f"/campaigns/{seeded}/interdict", json={"k": 5, "backend": "cpsat"}).json()
    assert plan["valid"] and plan["backend"] == "cpsat" and not plan["fell_back"]
    assert 0 < len(plan["targets"]) <= 5 and plan["solve_ms"] < 1000
    assert {t["kind"] for t in plan["targets"]} <= {"ip", "nameserver", "registrar"}
    assert {t["takedown_route"] for t in plan["targets"]} <= {"hosting", "dns", "registrar"}
    assert plan["qubit_count"] is None and plan["domains_total"] == 60
    assert sum(t["kills"] for t in plan["targets"]) == plan["domains_killed"] == len(plan["killed_domain_ids"])
    assert [t["rank"] for t in plan["targets"]] == list(range(1, len(plan["targets"]) + 1))
    assert api.get(f"/plans/{plan['plan_id']}").json()["plan_id"] == plan["plan_id"]


def test_interdict_k_too_large_is_422_problem_with_max(api, seeded):
    r = api.post(f"/campaigns/{seeded}/interdict", json={"k": 999, "backend": "cpsat"})
    assert r.status_code == 422 and r.headers["content-type"].startswith(PROBLEM)
    assert "max" in r.json()["detail"]
    assert api.post(f"/campaigns/{seeded}/interdict", json={"k": 0}).status_code == 422


def test_interdict_unknown_backend_and_campaign(api, seeded):
    assert api.post(f"/campaigns/{seeded}/interdict", json={"k": 2, "backend": "magic"}).status_code == 422
    r = api.post("/campaigns/00000000-0000-0000-0000-000000000000/interdict", json={"k": 2})
    assert r.status_code == 404 and r.headers["content-type"].startswith(PROBLEM)


def test_interdict_without_takedownable_infra_is_409(api, db):
    cid = db.execute(sa.text("insert into campaigns (label, domain_count) values ('CAMP-X', 2) returning id")).scalar()
    node = db.execute(sa.text("insert into infra_nodes (kind, value) values ('kit_hash', 'k') returning id")).scalar()
    for n in ("a.example", "b.example"):
        d = db.execute(sa.text("insert into domains (name, etld1, campaign_id) values (:n, :n, :c) returning id"),
                       {"n": n, "c": cid}).scalar()
        db.execute(sa.text("insert into graph_edges (domain_id, node_id, weight) values (:d, :n, 1.0)"),
                   {"d": d, "n": node})
    r = api.post(f"/campaigns/{cid}/interdict", json={"k": 2})
    assert r.status_code == 409 and "No shared infrastructure" in r.json()["detail"]


def test_benchmark_all_rows_one_best(api, seeded):
    plan = api.post(f"/campaigns/{seeded}/interdict", json={"k": 3}).json()
    rows = api.post(f"/plans/{plan['plan_id']}/benchmark").json()["rows"]
    assert [r["backend"] for r in rows] == ["cpsat", "qaoa", "annealing", "greedy"]
    assert sum(r["is_best"] for r in rows) == 1
    q = next(r for r in rows if r["backend"] == "qaoa")
    assert q["qubit_count"] is None or q["qubit_count"] == q["n_variables"]


def test_graph_marks_targets_after_plan(api, seeded):
    api.post(f"/campaigns/{seeded}/interdict", json={"k": 3})
    g = api.get(f"/campaigns/{seeded}/graph").json()
    nodes = g["elements"]["nodes"]
    assert any(n["data"].get("is_target") for n in nodes) and not g["truncated"]
    dom = [n for n in nodes if n["data"]["kind"] == "domain"]
    assert len(dom) == 60 and all(n["data"]["status"] == "confirmed" for n in dom)
    ids = {n["data"]["id"] for n in nodes}
    assert all(e["data"]["source"] in ids and e["data"]["target"] in ids for e in g["elements"]["edges"])


def _bundle(api):
    d = api.get("/candidates?status=confirmed&limit=1").json()["items"][0]
    full = api.get(f"/domains/{d['id']}").json()
    return full, full["evidence_bundle_id"]


def test_domain_detail_has_reasons_and_bundle(api, seeded):
    full, bid = _bundle(api)
    assert full["confirmation"]["strong_count"] >= 2 and full["confirmation"]["signals"]
    assert full["triage"]["provenance"] == "rules" and full["triage"]["reasons"]
    assert full["enrichment"]["ip_addresses"] and bid and full["source"] == "seed"


def test_tamper_demo_names_the_file(api, seeded, db):
    _, bid = _bundle(api)
    ev = api.get(f"/evidence/{bid}").json()
    assert {a["name"] for a in ev["artifacts"]} >= {"dom.html", "meta.json"} and ev["partial"] is True
    assert api.post(f"/evidence/{bid}/verify").json()["valid"] is True
    d = db.execute(sa.text("select artifact_dir from evidence_bundles where id=:b"), {"b": bid}).scalar()
    path = Path(d) / "dom.html"
    data = bytearray(path.read_bytes())
    data[10] ^= 1
    path.write_bytes(bytes(data))
    r = api.post(f"/evidence/{bid}/verify").json()
    assert r["valid"] is False and r["root_matches"] is False and r["signature_valid"] is True
    assert r["failures"][0]["artifact"] == "dom.html" and r["failures"][0]["reason"] == "hash_mismatch"


def test_artifact_download_and_purged_404(api, seeded, db):
    _, bid = _bundle(api)
    assert api.get(f"/evidence/{bid}/artifacts/dom.html").status_code == 200
    assert api.get(f"/evidence/{bid}/artifacts/..%2F..%2Fsecret").status_code == 404
    d = Path(db.execute(sa.text("select artifact_dir from evidence_bundles where id=:b"), {"b": bid}).scalar())
    (d / "dom.html").unlink()
    r = api.get(f"/evidence/{bid}/artifacts/dom.html")
    assert r.status_code == 404 and "hashes retained" in r.json()["detail"]


def test_report_never_sent(api, seeded):
    _, bid = _bundle(api)
    rep = api.get(f"/evidence/{bid}/report").json()
    assert rep["sent"] is False and rep["format"] == "markdown" and "not sent" in rep["body"]


def test_stream_mode_switch_and_state(api):
    r = api.post("/stream/mode", json={"mode": "replay", "speed": 2.0})
    assert r.status_code == 200 and r.json()["mode"] == "replay"
    assert api.post("/stream/mode", json={"mode": "bogus"}).status_code == 422


def test_metrics_and_ops_log(api, seeded):
    api.post(f"/campaigns/{seeded}/interdict", json={"k": 2})
    m = api.get("/metrics").json()
    assert m["campaigns_active"] == 1 and m["domains_confirmed"] == 60 and "anchor_queue_depth" in m
    log = api.get("/ops/log?channel=interdict").json()["items"]
    assert log and "cpsat" in log[0]["message"]


def test_force_confirm_queues(api, seeded):
    d = api.get("/candidates?limit=1").json()["items"][0]
    r = api.post(f"/domains/{d['id']}/confirm")
    assert r.status_code == 202 and r.json() == {"queued": True, "domain_id": d["id"]}


def test_unknown_domain_404_problem(api):
    r = api.get("/domains/999999999")
    assert r.status_code == 404 and r.headers["content-type"].startswith(PROBLEM) and r.json()["status"] == 404


async def test_live_feed_throttled_to_20_per_second():
    import fakeredis.aioredis as fr

    from services.api.routes.stream import live_events
    r = fr.FakeRedis(decode_responses=True)
    out = []

    async def consume():
        async for chunk in live_events(r, max_per_sec=20, heartbeat_s=60):
            if chunk.startswith("event: cert"):
                out.append(chunk)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.2)
    for i in range(300):
        await r.publish("certs:live", json.dumps({"name": f"d{i}.example", "is_candidate": False}))
    await asyncio.sleep(1.0)
    task.cancel()
    assert 0 < len(out) <= 22


async def test_stale_heartbeat_reads_as_down():
    from datetime import datetime, timedelta, timezone

    import fakeredis.aioredis as fr

    from services.api.routes.stream import read_state
    r = fr.FakeRedis(decode_responses=True)
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    await r.hset("stream:state", mapping={"mode": "live", "connection": "connected", "certs_per_sec": "544",
                                          "last_heartbeat": old})
    st = await read_state(r)
    assert st.connection == "down" and st.certs_per_sec == 0
    fresh = datetime.now(timezone.utc).isoformat()
    await r.hset("stream:state", "last_heartbeat", fresh)
    assert (await read_state(r)).connection == "connected"
