"""scripts/demo.py: the pure parts that decide what is warmed and what counts as ready."""
from scripts.demo import env_keys, failures, largest


def test_env_keys_reads_only_qcc_keys(tmp_path):
    p = tmp_path / ".env"
    p.write_text('DATABASE_URL=postgresql://x\nQCC_KEY_ORG1=qcc_org_a\nQCC_KEY_ADMIN="qcc_admin_b"\n# QCC_KEY_X=no\n',
                 encoding="utf-8")
    assert env_keys(p) == {"QCC_KEY_ORG1": "qcc_org_a", "QCC_KEY_ADMIN": "qcc_admin_b"}


def test_largest_campaign_is_warmed():
    assert largest([{"id": "a", "domain_count": 12}, {"id": "b", "domain_count": 470}])["id"] == "b"
    assert largest([]) is None


def test_any_non_200_is_a_failure_including_unreachable():
    rows = [("GET /status", 200, 5.0), ("GET /campaigns/x/graph", 500, 9.0), ("GET /health", 0, 1.0)]
    assert [r[0] for r in failures(rows)] == ["GET /campaigns/x/graph", "GET /health"]


async def test_flush_drops_only_the_pending_fetch_backlog():
    """Demo-day operation: pending fetches and scheduled re-checks are dropped (those domains stay candidates);
    nothing else in Redis is touched."""
    import fakeredis.aioredis as fr

    from scripts.demo import flush_backlog
    r = fr.FakeRedis(decode_responses=True)
    await r.rpush("enrich:queue", "1:10", "1:11")
    await r.zadd("enrich:retry", {"force:1:12": 1.0})
    await r.hset("stream:mode", mapping={"mode": "live"})
    out = await flush_backlog(r)
    assert out == {"queued": 2, "scheduled_rechecks": 1}
    assert await r.llen("enrich:queue") == 0 and await r.zcard("enrich:retry") == 0
    assert await r.hget("stream:mode", "mode") == "live"
