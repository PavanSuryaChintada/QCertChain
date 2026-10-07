"""API keys (T2, T5): every route except /health needs a key; demo keys are read-only; the admin key reads no
org data; keys are stored hashed and never in plaintext."""
import pytest
import sqlalchemy as sa

from services.api import auth


@pytest.mark.db
def test_unauthenticated_rejected_everywhere_except_health(api):
    from services.api.main import app
    bare = {auth.HEADER: ""}
    assert api.get("/health", headers=bare).status_code == 200
    checked = 0
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        if route.path == "/health" or not methods:
            continue
        path = route.path.replace("{", "").replace("}", "")  # any placeholder value: auth runs first
        for m in methods - {"HEAD", "OPTIONS"}:
            r = api.request(m, path, headers=bare)
            assert r.status_code == 401, (m, route.path, r.status_code)
            assert r.headers.get("www-authenticate") == auth.HEADER
            checked += 1
    assert checked >= 20
    assert api.get("/candidates", headers={auth.HEADER: "qcc_org_not-a-real-key"}).status_code == 401


@pytest.mark.db
def test_no_public_api_docs(api):
    for p in ("/docs", "/openapi.json", "/redoc"):
        assert api.get(p, headers={auth.HEADER: ""}).status_code in (401, 404)


@pytest.mark.db
def test_keys_are_stored_hashed_never_plaintext(api, db):
    rows = db.execute(sa.text("select key_hash, prefix from api_keys")).all()
    assert len(rows) == 4
    for token in api.keys.values():
        assert all(token != r.key_hash and token not in r.key_hash for r in rows)
        assert auth.hash_key(token) in {r.key_hash for r in rows}
        assert len(token) > 40 and token.startswith("qcc_")


@pytest.mark.db
def test_demo_key_is_read_only_for_its_org(api, seeded):
    demo = api.as_("demo1")
    assert api.get(f"/campaigns/{seeded}", headers=demo).status_code == 200
    assert api.get("/campaigns", headers=demo).json()["total"] == 1
    assert api.get(f"/campaigns/{seeded}", headers=api.as_("org2")).status_code == 404  # the demo org is org1 only
    bid = api.get(f"/domains/{_a_domain(api, seeded)}").json()["evidence_bundle_id"]
    assert api.get(f"/evidence/{bid}/verify", headers=demo).json()["valid"] is True  # verification is a GET


@pytest.mark.db
def test_demo_key_gets_405_on_every_write_verb_of_every_route(api):
    """S4: the published demo key can read and nothing else — every non-GET verb on every route is 405."""
    from fastapi.routing import APIRoute

    from services.api.main import app
    demo = api.as_("demo1")
    checked = 0
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.path == "/health":
            continue
        path = route.path.replace("{", "").replace("}", "")
        for verb in ("POST", "PUT", "PATCH", "DELETE"):
            r = api.request(verb, path, headers=demo, json={})
            assert r.status_code == 405, (verb, route.path, r.status_code)
            checked += 1
    assert checked >= 80


@pytest.mark.db
def test_admin_key_reads_no_org_data_and_org_keys_have_no_admin(api, seeded):
    admin = api.as_("admin")
    for path in (f"/campaigns/{seeded}", "/campaigns", "/candidates", "/email/analyses", "/metrics", "/ops/log"):
        assert api.get(path, headers=admin).status_code == 404, path
    assert api.post("/admin/seed", json={"label": "x", "domains": 4}).status_code == 404  # org1 key
    assert api.post("/admin/stream/mode", json={"mode": "replay"}).status_code == 404
    assert api.post("/admin/stream/mode", json={"mode": "replay", "speed": 2.0}, headers=admin).status_code == 200


@pytest.mark.db
def test_revoked_key_stops_working(api, db):
    token = auth.create_key(db, "org", "org2")
    assert api.get("/campaigns", headers={auth.HEADER: token}).status_code == 200
    db.execute(sa.text("update api_keys set revoked_at = now() where key_hash = :h"), {"h": auth.hash_key(token)})
    auth.clear_cache()
    assert api.get("/campaigns", headers={auth.HEADER: token}).status_code == 401


@pytest.mark.db
def test_ledger_writes_sign_as_the_keys_org_and_reject_as_org(api, seeded):
    r = api.post("/ledger/attest", json={"subject_hash": "ab" * 32, "verdict": "disputed"}, headers=api.as_("org2"))
    assert r.status_code == 202 and r.json()["as_org"] == "org2"
    forged = api.post("/ledger/attest", json={"subject_hash": "ab" * 32, "verdict": "confirmed", "as_org": "org1"},
                      headers=api.as_("org2"))
    assert forged.status_code == 422


def _a_domain(api, campaign_id) -> int:
    g = api.get(f"/campaigns/{campaign_id}/graph").json()
    return int(next(n["data"]["id"] for n in g["elements"]["nodes"] if n["data"]["kind"] == "domain")[2:])


@pytest.mark.db
def test_rate_limit_returns_429_with_retry_after(api):
    """S5: demo 60/min, org 600/min, admin 60/min — per key, fixed window, shared via Redis."""
    from services.config import SETTINGS
    assert (SETTINGS.rate_limit_demo, SETTINGS.rate_limit_org, SETTINGS.rate_limit_admin) == (60, 600, 60)
    object.__setattr__(SETTINGS, "rate_limit_demo", 5)  # frozen settings: shrink the window for the test
    try:
        demo = api.as_("demo1")
        codes = [api.get("/campaigns", headers=demo).status_code for _ in range(7)]
        assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
        r = api.get("/campaigns", headers=demo)
        assert r.status_code == 429 and 1 <= int(r.headers["retry-after"]) <= 60
        assert api.get("/campaigns").status_code == 200  # another key has its own budget
    finally:
        object.__setattr__(SETTINGS, "rate_limit_demo", 60)


@pytest.mark.db
def test_limiter_outage_does_not_take_the_api_down(api):
    from services.api import deps, main

    class Down:
        async def incr(self, *a):
            raise ConnectionError("redis down")
    main.app.dependency_overrides[deps.get_redis] = lambda: Down()
    assert api.get("/campaigns").status_code == 200
