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


def test_up_starts_only_what_is_not_already_running():
    from scripts.demo import services_to_start
    alive = {"chain": True, "api": False, "console": True, "ingest": False, "triage": True, "enrich": False,
             "anchor": True, "tunnel": True}
    assert services_to_start(alive) == ["api", "ingest", "enrich"]


def test_the_public_tunnel_is_started_and_revived_like_the_workers():
    """Spec 2026-10-09 §10: a dead quick tunnel is restarted by the supervisor, which publishes the new URL."""
    from scripts.demo_stack import alive_map, services_to_start
    assert alive_map([(1, "python -m scripts.tunnel")])["tunnel"]
    running = {k: True for k in ("api", "console", "ingest", "triage", "enrich", "anchor")}
    assert services_to_start({**running, "tunnel": False}) == ["tunnel"]


def test_a_fresh_chain_needs_deploy_and_reset_an_old_one_only_warming():
    from scripts.demo import chain_plan
    assert chain_plan(chain_was_running=False, contracts_deployed=False) == ["deploy", "reset"]
    assert chain_plan(chain_was_running=True, contracts_deployed=True) == ["warm"]
    assert chain_plan(chain_was_running=True, contracts_deployed=False) == ["deploy", "reset"]


def test_pidfiles_round_trip(tmp_path):
    from scripts.demo import read_pid, write_pid
    write_pid(tmp_path, "api", 4242)
    assert read_pid(tmp_path, "api") == 4242 and read_pid(tmp_path, "nope") is None


def test_supervisor_revives_dead_services_by_process_not_by_http():
    """A busy API that is slow to answer is NOT restarted (that would clash on its port): liveness is the process."""
    from scripts.demo_stack import API, CONSOLE, WORKERS, alive_map
    procs = [(1, f"python -m {API[1]} --port 8000"), (2, f"python -m scripts.e2e_stack --serve x/apps/console/{CONSOLE[1]}"),
             (3, "python -m services.ingest.stream")]
    alive = alive_map(procs)
    assert alive["api"] and alive["console"] and alive["ingest"]
    assert not alive["triage"] and not alive["enrich"] and not alive["anchor"]


def test_offline_e2e_console_does_not_mask_a_dead_demo_console():
    from scripts.demo_stack import alive_map
    assert not alive_map([(9, r"python -m scripts.e2e_stack --serve C:\x\apps\console\dist-e2e 4173")])["console"]
