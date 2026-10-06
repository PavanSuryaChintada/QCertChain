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
