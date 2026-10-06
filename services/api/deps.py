"""FastAPI dependencies. Tests override every one of these."""
from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

import redis.asyncio as aioredis
import sqlalchemy as sa

from services.api.db import engine
from services.config import SETTINGS


def get_conn() -> Iterator[sa.Connection]:
    """One transaction per request: committed on success, rolled back on any error."""
    with engine().begin() as c:
        yield c


@lru_cache(maxsize=1)
def _redis():
    return aioredis.from_url(SETTINGS.redis_url, decode_responses=True)


def get_redis():
    return _redis()


def get_evidence_dir() -> str:
    return SETTINGS.evidence_dir


def get_signing_key() -> str:
    return SETTINGS.collector_private_key
