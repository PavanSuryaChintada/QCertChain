"""Per-endpoint server-side latency, kept in memory for /health (T17): p50/p95 over the last 5 minutes.

A pure ASGI middleware (not BaseHTTPMiddleware: that buffers streaming responses and would break the SSE feed).
Latency is measured from request start to the end of the response body, keyed by the ROUTE TEMPLATE
(`/campaigns/{campaign_id}`), never the concrete path, so ids never become metric labels.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

WINDOW_S = 300
MAX_SAMPLES = 2000  # per endpoint

_samples: dict[str, deque[tuple[float, float]]] = defaultdict(lambda: deque(maxlen=MAX_SAMPLES))
_lock = threading.Lock()


def record(key: str, ms: float, now: float | None = None) -> None:
    with _lock:
        _samples[key].append((now if now is not None else time.monotonic(), ms))


def _pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def summary(now: float | None = None) -> dict[str, dict]:
    now = now if now is not None else time.monotonic()
    out = {}
    with _lock:
        items = {k: [ms for t, ms in v if now - t <= WINDOW_S] for k, v in _samples.items()}
    for k, xs in sorted(items.items()):
        if xs:
            out[k] = {"count": len(xs), "p50_ms": round(_pct(xs, 0.5), 1), "p95_ms": round(_pct(xs, 0.95), 1)}
    return out


def reset() -> None:
    with _lock:
        _samples.clear()


class TimingMiddleware:
    SKIP = ("/certs/live",)  # a stream's duration is its lifetime, not a latency

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        t0 = time.perf_counter()
        status = {"code": 0}

        async def wrapped(msg):
            if msg["type"] == "http.response.start":
                status["code"] = msg["status"]
            await send(msg)
        try:
            await self.app(scope, receive, wrapped)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", None)
            if path and path not in self.SKIP and status["code"] < 500:
                record(f"{scope['method']} {path}", (time.perf_counter() - t0) * 1000)
