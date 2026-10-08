"""S3c: the runtime kill switch for S1/S2. It can only LOWER a configured strength, never raise it."""
import fakeredis.aioredis as fr

from services.enrich import signal_switch as sw


def test_override_can_only_lower_a_strength():
    conf = {"exfil": "strong", "js_post": "moderate"}
    assert sw.effective(conf, {}) == conf
    assert sw.effective(conf, {"exfil": "off", "js_post": "off"}) == {"exfil": "off", "js_post": "off"}
    assert sw.effective(conf, {"js_post": "strong"}) == conf          # a runtime switch never promotes past the gate
    assert sw.effective(conf, {"exfil": "bogus"}) == conf            # invalid values are ignored


async def test_current_reads_the_redis_override():
    r = fr.FakeRedis(decode_responses=True)
    conf = sw.configured()
    assert await sw.current(r) == conf
    await sw.set_override(r, {"exfil": "off"})
    assert (await sw.current(r))["exfil"] == "off"
    await sw.clear(r)
    assert await sw.current(r) == conf


async def test_override_works_on_a_client_that_returns_bytes():
    """A kill switch must not fail silently: a Redis client without decode_responses returns bytes."""
    r = fr.FakeRedis(decode_responses=False)
    await sw.set_override(r, {"exfil": "off"})
    assert (await sw.current(r))["exfil"] == "off"
