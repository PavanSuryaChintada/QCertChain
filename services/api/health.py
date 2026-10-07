"""/health content (T17, S8): per-endpoint latency, where the API and the database run, and the measured round trip
between them. Shown on screen so co-location is visible, not asserted."""
from __future__ import annotations

import os
import re
import threading
import time
from urllib.parse import urlsplit

import sqlalchemy as sa

from services.api import timing
from services.config import SETTINGS

# Provider region names -> city, so "is the API next to the database?" is answerable at a glance.
CITY = {"ap-southeast-1": "Singapore", "asia-southeast1": "Singapore", "asia-southeast1-eqsg3a": "Singapore",
        "sin1": "Singapore", "us-east-1": "N. Virginia", "us-west-1": "N. California", "us-west2": "Oregon",
        "eu-west-1": "Ireland", "eu-central-1": "Frankfurt", "europe-west4": "Netherlands",
        "ap-south-1": "Mumbai", "local": "this machine"}
RTT_TTL_S = 30.0

_rtt: dict = {"at": 0.0, "value": None}
_lock = threading.Lock()


def database_region(url: str) -> str:
    """Supabase pooler hosts carry the region: aws-0-ap-southeast-1.pooler.supabase.com."""
    host = urlsplit(url.replace("postgresql+psycopg://", "postgresql://")).hostname or ""
    m = re.search(r"aws-\d+-([a-z]{2}-[a-z]+-\d)\.pooler\.supabase\.com", host)
    if m:
        return m.group(1)
    return "local" if host in ("localhost", "127.0.0.1", "postgres", "") else host


def api_region() -> str:
    return os.environ.get("API_REGION") or os.environ.get("RAILWAY_REPLICA_REGION") or "local"


def db_round_trip_ms(engine_factory) -> float | None:
    """Median of 5 `select 1` round trips, cached for 30 s so /health stays cheap. None if the database is down."""
    now = time.monotonic()
    with _lock:
        if now - _rtt["at"] < RTT_TTL_S:
            return _rtt["value"]
    value = None
    try:
        with engine_factory().connect() as c:
            xs = []
            for _ in range(5):
                t = time.perf_counter()
                c.execute(sa.text("select 1")).scalar()
                xs.append((time.perf_counter() - t) * 1000)
            value = round(sorted(xs)[2], 1)
    except Exception:
        value = None
    with _lock:
        _rtt.update(at=now, value=value)
    return value


def report(engine_factory=None) -> dict:
    if engine_factory is None:
        from services.api.db import engine as engine_factory
    api, db = api_region(), database_region(SETTINGS.database_url)
    rtt = db_round_trip_ms(engine_factory) if SETTINGS.database_url else None
    return {
        "status": "ok" if rtt is not None or not SETTINGS.database_url else "degraded",
        "service": "qcertchain-api",
        "regions": {"api": api, "api_city": CITY.get(api, api), "database": db, "database_city": CITY.get(db, db),
                    "colocated": CITY.get(api, api) == CITY.get(db, db)},
        "database_round_trip_ms": rtt,
        "endpoints": timing.summary(),  # p50/p95 per route template over the last 5 minutes
        "window_s": timing.WINDOW_S,
    }
