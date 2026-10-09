"""The public home page's live certificate panel (owner decision 2026-10-10): certificate-log names only, and a
candidate's name masked on the server, so its full name never reaches a browser (CLAUDE.md §2.2: a name match is a
candidate, not a verdict). No database: fakeredis."""
import json
from datetime import datetime, timezone

import fakeredis.aioredis as fr

from services.api.workers.triage_worker import Batch, publish

TS = datetime(2026, 10, 10, tzinfo=timezone.utc).isoformat()


def item(name, etld1, *, candidate=False, source="live"):
    return {"ts": TS, "name": name, "etld1": etld1, "score": 0.9 if candidate else 0.1, "is_candidate": candidate,
            "domain_id": 7 if candidate else None, "issuer": "Let's Encrypt", "source": source}


def test_mask_hides_most_of_the_name_and_every_subdomain():
    from services.api.routes.public import mask
    assert mask("login.sbi-kyc-verify.top", "sbi-kyc-verify.top") == "sbi-k••••••.top"
    assert mask("secure.sbi-verify.co.in", "sbi-verify.co.in") == "sbi-v••••••.co.in"
    assert mask("a.b.short.xyz", None) == "sh••••••.xyz"  # no etld1: the last two labels, never the subdomains
    assert "login" not in mask("login.sbi-kyc-verify.top", "sbi-kyc-verify.top")


async def test_only_certificate_log_names_reach_the_public_lists():
    r = fr.FakeRedis(decode_responses=True)
    b = Batch({})
    b.add_feed(item("cdn.northwind.com", "northwind.com"))
    b.add_feed(item("sbi-kyc-verify.top", "sbi-kyc-verify.top", candidate=True))
    b.add_feed(item("old.replayed.net", "replayed.net", source="replay"))
    b.add_feed(item("hdfc-login.example", "hdfc-login.example", candidate=True, source="email"))  # an org's email
    b.add_feed(item("seeded-kit.example", "seeded-kit.example", candidate=True, source="seed"))  # demo data
    await publish(r, b)
    assert [json.loads(x)["name"] for x in await r.lrange("certs:recent", 0, -1)] == ["old.replayed.net",
                                                                                      "cdn.northwind.com"]
    assert [json.loads(x)["name"] for x in await r.lrange("certs:recent_candidates", 0, -1)] == ["sbi-kyc-verify.top"]


async def test_the_public_lists_stay_short():
    r = fr.FakeRedis(decode_responses=True)
    b = Batch({})
    for i in range(40):
        b.add_feed(item(f"site{i}.com", f"site{i}.com"))
        b.add_feed(item(f"sbi-verify{i}.top", f"sbi-verify{i}.top", candidate=True))
    await publish(r, b)
    names = [json.loads(x)["name"] for x in await r.lrange("certs:recent", 0, -1)]
    assert names[0] == "site39.com" and len(names) == 6  # newest first
    assert await r.llen("certs:recent_candidates") == 3


async def test_the_public_feed_never_carries_a_candidates_full_name():
    from services.api.routes.public import public_feed
    r = fr.FakeRedis(decode_responses=True)
    await r.hset("stream:state", mapping={"mode": "live", "connection": "connected", "certs_per_sec": "3100",
                                          "last_heartbeat": datetime.now(timezone.utc).isoformat()})
    b = Batch({})
    b.add_feed(item("cdn.northwind.com", "northwind.com"))
    b.add_feed(item("login.icici-netbanking-verify.top", "icici-netbanking-verify.top", candidate=True))
    await publish(r, b)
    out = await public_feed(r)
    assert out["mode"] == "live" and out["connection"] != "down"
    assert out["recent"] == [{"name": "cdn.northwind.com", "ts": TS}]
    assert out["candidates"] == [{"name": "icici••••••.top", "ts": TS}]
    text = json.dumps(out, ensure_ascii=False)
    for leak in ("icici-netbanking", "login.", "score", "domain_id", "issuer"):
        assert leak not in text


def test_the_public_feed_needs_no_key(monkeypatch):
    import fakeredis
    from fastapi.testclient import TestClient
    from services.api import deps, main
    from services.api.routes import public
    server = fakeredis.FakeServer()
    main.app.dependency_overrides[deps.get_redis] = lambda: fr.FakeRedis(server=server, decode_responses=True)
    monkeypatch.setattr(public, "_cache", None)
    try:
        r = TestClient(main.app).get("/certs/public")
    finally:
        main.app.dependency_overrides.pop(deps.get_redis, None)
    assert r.status_code == 200
    assert r.json()["recent"] == [] and r.json()["connection"] == "down"
