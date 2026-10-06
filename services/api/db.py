"""SQLAlchemy engine. The app database is Supabase (session pooler, IPv4); tests use a local postgres:17."""
from __future__ import annotations

from functools import lru_cache

import sqlalchemy as sa

from services.config import SETTINGS


@lru_cache(maxsize=1)
def engine() -> sa.Engine:
    if not SETTINGS.database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return sa.create_engine(SETTINGS.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5,
                            pool_recycle=300)
