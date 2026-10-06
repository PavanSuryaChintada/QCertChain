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
    conn = db_engine.connect()
    tx = conn.begin()
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

    from services.api import deps, main

    server = fakeredis.FakeServer()
    key = nacl.signing.SigningKey.generate().encode().hex()

    def conn():
        yield db

    main.app.dependency_overrides[deps.get_conn] = conn
    main.app.dependency_overrides[deps.get_redis] = lambda: fakeredis.aioredis.FakeRedis(server=server,
                                                                                         decode_responses=True)
    main.app.dependency_overrides[deps.get_evidence_dir] = lambda: tmp_path
    main.app.dependency_overrides[deps.get_signing_key] = lambda: key
    with TestClient(main.app) as c:
        c.fake_redis_server = server
        yield c
    main.app.dependency_overrides.clear()


@pytest.fixture
def seeded(api):
    r = api.post("/seed/campaign", json={"label": "smoke", "domains": 60, "ips": 12, "asns": 3, "nameservers": 4})
    assert r.status_code == 200, r.text
    return r.json()["id"]
