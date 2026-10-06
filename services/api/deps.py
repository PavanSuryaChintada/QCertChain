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


class UnavailableLedger:
    """Stand-in when the chain or its deployment file is missing: every read reports 'unavailable'."""

    def __init__(self, reason: str):
        self.reason = reason
        self.accounts: dict = {}

    def available(self) -> bool:
        return False


@lru_cache(maxsize=1)
def _ledger():
    from services.api.ledger_service import Ledger
    try:
        return Ledger.from_settings(SETTINGS)
    except Exception as e:  # missing deployments/abi: the API still serves everything else
        return UnavailableLedger(f"{type(e).__name__}: {e}")


def get_ledger():
    return _ledger()
