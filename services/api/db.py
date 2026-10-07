"""SQLAlchemy engine and tenant scoping. The app database is Supabase (session pooler, IPv4); tests use a
local postgres:17.

Tenant isolation is enforced by the DATABASE, not by remembering a WHERE clause: `bind_org` switches the
transaction to role qcc_app with app.org_id set, and row-level security filters every org-owned table.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import sqlalchemy as sa

from services.config import SETTINGS


@lru_cache(maxsize=1)
def engine() -> sa.Engine:
    if not SETTINGS.database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return sa.create_engine(SETTINGS.database_url, pool_pre_ping=True, pool_size=SETTINGS.db_pool_size,
                            max_overflow=SETTINGS.db_pool_overflow, pool_recycle=300)


def bind_org(c: sa.Connection, org_id: int | None) -> None:
    """Scope the current transaction to one org (None = no org: sees only shared rows)."""
    c.execute(sa.text("select set_config('app.org_id', :o, true)"), {"o": str(org_id) if org_id else ""})
    c.execute(sa.text("set local role qcc_app"))


def unbind_org(c: sa.Connection) -> None:
    """Undo bind_org inside a still-open transaction (tests share one transaction across requests)."""
    c.execute(sa.text("reset role"))
    c.execute(sa.text("select set_config('app.org_id', '', true)"))


def set_org_context(c: sa.Connection, org_id: int | None) -> None:
    """Privileged connection that writes on behalf of an org: org_id column defaults resolve to it.
    Used by trusted platform processes (workers, admin seed) — the request path always uses bind_org."""
    c.execute(sa.text("select set_config('app.org_id', :o, true)"), {"o": str(org_id) if org_id else ""})


@contextmanager
def org_transaction(org_id: int) -> Iterator[sa.Connection]:
    """A worker's unit of work on behalf of one org, under the same RLS as an API request."""
    with engine().begin() as c:
        bind_org(c, org_id)
        yield c
