import os

import pytest
import sqlalchemy as sa

from scripts.apply_schema import apply
from services.config import SETTINGS

TEST_URL = os.environ.get("TEST_DATABASE_URL", SETTINGS.test_database_url)


@pytest.fixture(scope="session")
def db_engine():
    assert "supabase" not in TEST_URL, "tests must never run against Supabase"
    eng = sa.create_engine(TEST_URL)
    with eng.begin() as c:
        c.exec_driver_sql("drop schema public cascade; create schema public;")
    apply(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def db(db_engine):
    """Privileged connection in a rolled-back transaction, writing on behalf of org1 (org_id defaults)."""
    from services.api.db import set_org_context
    conn = db_engine.connect()
    tx = conn.begin()
    set_org_context(conn, 1)
    yield conn
    tx.rollback()
    conn.close()


@pytest.fixture
def api(db, tmp_path):
    """FastAPI TestClient bound to the rolled-back test transaction, fake Redis, temp evidence dir."""
    import fakeredis
    import fakeredis.aioredis
    import nacl.signing
    from fastapi.testclient import TestClient

    from services.api import auth, deps, main
    from services.api.db import set_org_context, unbind_org

    server = fakeredis.FakeServer()
    key = nacl.signing.SigningKey.generate().encode().hex()
    auth.clear_cache()
    keys = {"org1": auth.create_key(db, "org", "org1"), "org2": auth.create_key(db, "org", "org2"),
            "demo1": auth.create_key(db, "demo", "org1"), "admin": auth.create_key(db, "admin", None)}

    def conn():
        try:
            yield db
        finally:  # the test shares ONE transaction across requests: undo the request's scope, even on errors
            if db.in_transaction():
                unbind_org(db)
                set_org_context(db, 1)  # back to the fixture's default

    main.app.dependency_overrides[deps.get_conn] = conn
    main.app.dependency_overrides[deps.get_redis] = lambda: fakeredis.aioredis.FakeRedis(server=server,
                                                                                         decode_responses=True)
    main.app.dependency_overrides[deps.get_evidence_dir] = lambda: tmp_path
    main.app.dependency_overrides[deps.get_signing_key] = lambda: key
    # creating an organisation provisions it in a background thread on the REAL database: never in tests
    from services.api.routes import superadmin as superadmin_routes
    main.app.dependency_overrides[superadmin_routes.get_provisioner] = lambda: (lambda slug: None)
    with TestClient(main.app, headers={auth.HEADER: keys["org1"]}) as c:
        c.fake_redis_server = server
        c.keys = keys
        c.as_ = lambda who: {auth.HEADER: keys[who]}
        yield c
    main.app.dependency_overrides.clear()
    auth.clear_cache()


@pytest.fixture
def seeded(api):
    r = api.post("/admin/seed", headers=api.as_("admin"),
                 json={"label": "smoke", "domains": 60, "ips": 12, "asns": 3, "nameservers": 4, "org": "org1"})
    assert r.status_code == 200, r.text
    return r.json()["campaign_id"]


@pytest.fixture(autouse=True)
def _collector_key(monkeypatch):
    """Tests never depend on a developer's .env: if no collector signing key is configured, use a throwaway one."""
    import dataclasses

    import nacl.signing

    from services.api import seed
    if not seed.SETTINGS.collector_private_key:
        monkeypatch.setattr(seed, "SETTINGS", dataclasses.replace(
            seed.SETTINGS, collector_private_key=nacl.signing.SigningKey.generate().encode().hex()))
