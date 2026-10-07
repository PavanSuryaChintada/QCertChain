import asyncio
import json
from itertools import islice
from pathlib import Path

import fakeredis.aioredis as fr

from services.ingest.stream import STATE, STREAM, backoff_delays, run

FIX_LINE = json.dumps(json.loads((Path(__file__).parent / "fixtures/cert_update.json").read_text(encoding="utf-8")))


def test_backoff_caps_at_60():
    assert list(islice(backoff_delays(), 9)) == [1, 2, 4, 8, 16, 32, 60, 60, 60]


async def test_replay_dedups_and_labels_source(tmp_path):
    f = tmp_path / "cap.jsonl"
    f.write_text(FIX_LINE + "\n" + FIX_LINE + "\n", encoding="utf-8")  # same cert twice (two logs)
    r = fr.FakeRedis(decode_responses=True)
    stop = asyncio.Event()
    task = asyncio.create_task(run("replay", r, url="", replay_file=str(f), speed=1000, stop=stop))
    await asyncio.sleep(0.5)
    stop.set()
    await asyncio.wait_for(task, 5)
    entries = await r.xrange(STREAM)
    assert len(entries) == 1
    assert json.loads(entries[0][1]["cert"])["source"] == "replay"
    st = await r.hgetall(STATE)
    assert st["mode"] == "replay" and st["connection"] == "replay" and st["replay_file"] == str(f)


async def test_malformed_replay_line_skipped(tmp_path):
    f = tmp_path / "cap.jsonl"
    f.write_text("{not json\n" + FIX_LINE + "\n", encoding="utf-8")
    r = fr.FakeRedis(decode_responses=True)
    stop = asyncio.Event()
    task = asyncio.create_task(run("replay", r, url="", replay_file=str(f), speed=1000, stop=stop))
    await asyncio.sleep(0.5)
    stop.set()
    await asyncio.wait_for(task, 5)
    assert len(await r.xrange(STREAM)) == 1


async def test_live_unreachable_reports_reconnecting():
    r = fr.FakeRedis(decode_responses=True)
    stop = asyncio.Event()
    task = asyncio.create_task(run("live", r, url="ws://127.0.0.1:1/none", replay_file="", speed=1, stop=stop))
    await asyncio.sleep(0.6)
    stop.set()
    await asyncio.wait_for(task, 5)
    st = await r.hgetall(STATE)
    assert st["mode"] == "live" and st["connection"] == "reconnecting"


async def test_batched_records_all_flushed_on_stop(tmp_path):
    lines = []
    base = json.loads(FIX_LINE)
    for i in range(1500):  # distinct certs, more than one batch
        m = json.loads(json.dumps(base))
        m["data"]["leaf_cert"]["sha256"] = f"fp{i}"
        m["data"]["leaf_cert"]["all_domains"] = [f"d{i}.example.org"]
        m["data"].pop("seen", None)
        lines.append(json.dumps(m))
    f = tmp_path / "cap.jsonl"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    r = fr.FakeRedis(decode_responses=True)
    stop = asyncio.Event()
    task = asyncio.create_task(run("replay", r, url="", replay_file=str(f), speed=0, stop=stop))
    for _ in range(100):
        await asyncio.sleep(0.05)
        if await r.xlen(STREAM) >= 1500:
            break
    stop.set()
    await asyncio.wait_for(task, 5)
    assert await r.xlen(STREAM) == 1500


async def test_replay_throughput_uses_batched_writes(tmp_path, monkeypatch):
    calls = {"xadd": 0}
    r = fr.FakeRedis(decode_responses=True)
    real_xadd = r.xadd

    async def counting_xadd(*a, **kw):
        calls["xadd"] += 1
        return await real_xadd(*a, **kw)

    monkeypatch.setattr(r, "xadd", counting_xadd)
    base = json.loads(FIX_LINE)
    lines = []
    for i in range(1000):
        m = json.loads(json.dumps(base))
        m["data"]["leaf_cert"]["sha256"] = f"fp{i}"
        lines.append(json.dumps(m))
    f = tmp_path / "cap.jsonl"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    stop = asyncio.Event()
    task = asyncio.create_task(run("replay", r, url="", replay_file=str(f), speed=0, stop=stop))
    await asyncio.sleep(1.0)
    stop.set()
    await asyncio.wait_for(task, 5)
    assert calls["xadd"] == 0  # writes go through pipelines, never one round trip per cert


def test_stream_cap_fits_in_redis_memory():
    """Smoke-run finding: 1,000,000 entries x ~587 B (measured, MEMORY USAGE) = 560 MB > Redis maxmemory 512 MB with
    noeviction, so XADD failed and ingest died. The trim cap must fit with headroom for the other keys."""
    import re
    from pathlib import Path

    from services.ingest.stream import STREAM_MAXLEN
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    maxmem_mb = int(re.search(r"--maxmemory (\d+)mb", compose).group(1))
    measured_bytes_per_entry = 587
    assert STREAM_MAXLEN * measured_bytes_per_entry <= 0.6 * maxmem_mb * 1024 * 1024


async def test_replay_reports_the_virtual_clock(tmp_path):
    """Item 7: an accelerated replay shows the replayed certificates' ORIGINAL CT time, and the speed."""
    import asyncio
    import gzip
    import json

    import fakeredis.aioredis as fr

    from services.ingest.stream import STATE, run
    f = tmp_path / "fx.jsonl.gz"
    with gzip.open(f, "wt", encoding="utf-8") as out:
        for i, ts in enumerate((1791300000.0, 1791300060.0)):
            out.write(json.dumps({"message_type": "certificate_update", "data": {
                "seen": ts, "leaf_cert": {"all_domains": [f"x{i}.example"], "fingerprint": f"F{i}",
                                          "issuer": {"O": "Test CA"}, "not_before": 0, "not_after": 1,
                                          "serial_number": "01"}, "cert_index": i}}) + "\n")
    r = fr.FakeRedis(decode_responses=True)
    stop = asyncio.Event()
    task = asyncio.create_task(run("replay", r, url="", replay_file=str(f), speed=360.0, stop=stop))
    await asyncio.sleep(1.5)
    stop.set()
    await asyncio.wait_for(task, 5)
    st = await r.hgetall(STATE)
    assert st["replay_speed"] == "360" and st["virtual_time"].startswith("2026-10-06")
