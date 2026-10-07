"""CT consumer: live (self-hosted certstream websocket) or replay (capture.jsonl).

ONE process only — multiple consumers on the same stream duplicate work, they do not shard it.
Every emitted record is labelled with its source; the console shows the mode at all times.
"""
from __future__ import annotations

import asyncio
import contextlib
import gzip
import json
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis
import websockets

from services.config import SETTINGS
from services.ingest.certparse import SeenFingerprints, parse_message

STREAM, STATE, MODE_REQ = "certs:raw", "stream:state", "stream:mode_request"
HEARTBEAT_S = 5
BATCH_MAX = 500        # records per pipeline flush
FLUSH_EVERY_S = 0.1    # max latency added by batching
# Trim cap: ~587 B per entry measured, so 500k entries ~ 290 MB of the 512 MB Redis (noeviction). That is
# ~4.5 min of backlog at the measured 1,840 certs/s; triage keeps up, so the backlog is consumed history.
STREAM_MAXLEN = 500_000


def backoff_delays():
    d = 1
    while True:
        yield d
        d = 60 if d >= 32 else d * 2


class _Counter:
    def __init__(self):
        self.certs = self.names = 0
        self.t0 = time.time()

    def rates(self) -> tuple[float, float]:
        dt = max(time.time() - self.t0, 1e-6)
        out = (self.certs / dt, self.names / dt)
        self.certs = self.names = 0
        self.t0 = time.time()
        return out


class _Ctx:
    def __init__(self, r, mode: str, replay_file: str):
        self.r, self.mode, self.replay_file = r, mode, replay_file
        self.connection = "replay" if mode == "replay" else "reconnecting"
        self.seen = SeenFingerprints()
        self.ctr = _Counter()
        self.buf: list[str] = []
        self.virtual_ts: float | None = None  # replay: the original CT time of the certificate being replayed
        self.speed: float = 1.0

    async def emit(self, msg: dict) -> None:
        rec = parse_message(msg, "replay" if self.mode == "replay" else "certstream")
        if not rec or not rec.names or not self.seen.add(rec.fingerprint or rec.to_json()):
            return
        self.buf.append(rec.to_json())
        self.ctr.certs += 1
        self.ctr.names += len(rec.names)
        if len(self.buf) >= BATCH_MAX:
            await self.flush()

    async def flush(self) -> None:
        # One pipeline per batch: a round trip per certificate caps ingest near ~100/s.
        if not self.buf:
            return
        batch, self.buf = self.buf, []
        async with self.r.pipeline(transaction=False) as p:
            for item in batch:
                p.xadd(STREAM, {"cert": item}, maxlen=STREAM_MAXLEN, approximate=True)
            await p.execute()

    async def write_state(self) -> None:
        c, n = self.ctr.rates()
        await self.r.hset(STATE, mapping={
            "mode": self.mode,
            "connection": self.connection,
            "certs_per_sec": f"{c:.1f}",
            "names_per_sec": f"{n:.1f}",
            "replay_file": self.replay_file if self.mode == "replay" else "",
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            # the virtual clock: replayed certificates keep their real CT time; the UI shows it with the speed
            "virtual_time": (datetime.fromtimestamp(self.virtual_ts, timezone.utc).isoformat()
                             if self.mode == "replay" and self.virtual_ts else ""),
            "replay_speed": f"{self.speed:g}" if self.mode == "replay" else "",
        })


async def _flusher(ctx: _Ctx, stop: asyncio.Event) -> None:
    while not stop.is_set():
        await ctx.flush()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), FLUSH_EVERY_S)


async def _heartbeat(ctx: _Ctx, stop: asyncio.Event) -> None:
    while not stop.is_set():
        await ctx.write_state()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), HEARTBEAT_S)


async def _live(ctx: _Ctx, url: str, stop: asyncio.Event) -> None:
    delays = backoff_delays()
    while not stop.is_set():
        try:
            async with websockets.connect(url, max_size=2**24, open_timeout=20, close_timeout=1) as ws:
                ctx.connection = "connected"
                delays = backoff_delays()
                async for raw in ws:
                    with contextlib.suppress(json.JSONDecodeError):
                        await ctx.emit(json.loads(raw))
        except (OSError, asyncio.TimeoutError, websockets.WebSocketException):
            pass
        ctx.connection = "reconnecting"
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), next(delays))


async def _replay(ctx: _Ctx, path: str, speed: float, stop: asyncio.Event) -> None:
    while not stop.is_set():
        prev = None
        opener = gzip.open if path.endswith(".gz") else open  # long recordings are stored gzipped
        with opener(path, "rt", encoding="utf-8") as f:
            for line in f:
                if stop.is_set():
                    return
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = (msg.get("data") or {}).get("seen")
                if prev is not None and isinstance(ts, (int, float)) and speed > 0:
                    await asyncio.sleep(max(0.0, min((ts - prev) / speed, 2.0)))
                else:
                    await asyncio.sleep(0)
                prev = ts if isinstance(ts, (int, float)) else prev
                if isinstance(ts, (int, float)):
                    ctx.virtual_ts = ts
                await ctx.emit(msg)
        await asyncio.sleep(0.1)  # loop the capture


async def run(mode: str, r, *, url: str, replay_file: str, speed: float, stop: asyncio.Event) -> None:
    ctx = _Ctx(r, mode, replay_file)
    ctx.speed = speed
    await ctx.write_state()
    hb = asyncio.create_task(_heartbeat(ctx, stop))
    fl = asyncio.create_task(_flusher(ctx, stop))
    src = asyncio.create_task(_replay(ctx, replay_file, speed, stop) if mode == "replay"
                              else _live(ctx, url, stop))
    await asyncio.wait({src, asyncio.create_task(stop.wait())}, return_when=asyncio.FIRST_COMPLETED)
    stop.set()
    src.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await src
    await hb
    await fl
    await ctx.flush()  # nothing buffered is lost on stop or mode switch
    await ctx.write_state()


async def main() -> None:
    r = aioredis.from_url(SETTINGS.redis_url, decode_responses=True)
    while True:
        req = await r.hgetall(MODE_REQ)
        mode = req.get("mode") or SETTINGS.stream_mode
        speed = float(req.get("speed") or SETTINGS.replay_speed)
        stop = asyncio.Event()

        async def watch(current: str = mode) -> None:
            while not stop.is_set():
                await asyncio.sleep(2)
                if (await r.hget(MODE_REQ, "mode") or SETTINGS.stream_mode) != current:
                    stop.set()

        w = asyncio.create_task(watch())
        await run(mode, r, url=SETTINGS.certstream_url, replay_file=SETTINGS.replay_file, speed=speed, stop=stop)
        w.cancel()


if __name__ == "__main__":
    asyncio.run(main())
