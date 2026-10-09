"""The public site reaches the API through a Cloudflare quick tunnel whose URL changes on every start; the laptop
publishes the current URL in one row the console reads with the publishable key (spec 2026-10-09 §10)."""
import pytest
import sqlalchemy as sa

from scripts import tunnel

LINES = [
    "2026-10-09T11:45:22Z INF Requesting new quick Tunnel on trycloudflare.com...",
    "2026-10-09T11:45:25Z INF |  https://scenic-css-bedroom-minor.trycloudflare.com                                       |",
    '2026-10-09T11:41:19Z ERR Register tunnel error from server side error="Unauthorized: Tunnel not found"',
    'failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": dial tcp: lookup failed',
]


def test_the_tunnel_url_is_read_from_cloudflared_output():
    assert [tunnel.parse_url(line) for line in LINES] == [
        None, "https://scenic-css-bedroom-minor.trycloudflare.com", None, None]


@pytest.mark.db
def test_publishing_replaces_the_one_row_the_console_reads(db):
    tunnel.publish(db, "https://a-b.trycloudflare.com")
    tunnel.publish(db, "https://c-d.trycloudflare.com")
    rows = db.execute(sa.text("select name, url from public_endpoints")).all()
    assert [(r.name, r.url) for r in rows] == [("api", "https://c-d.trycloudflare.com")]


@pytest.mark.db
def test_the_publishable_key_reads_the_url_and_nothing_else(db):
    # Supabase's `anon` role (the publishable key) does not exist in the local test database: make it here.
    db.execute(sa.text("do $$ begin create role anon nologin; exception when duplicate_object then null; end $$"))
    db.execute(sa.text("grant usage on schema public to anon"))
    db.execute(sa.text("select qcc_public_endpoint_policy()"))
    tunnel.publish(db, "https://a-b.trycloudflare.com")
    db.execute(sa.text("set local role anon"))
    assert db.execute(sa.text("select url from public_endpoints where name = 'api'")).scalar() == \
        "https://a-b.trycloudflare.com"
    for stmt in ("insert into public_endpoints (name, url) values ('x', 'https://evil.example')",
                 "update public_endpoints set url = 'https://evil.example'",
                 "select * from super_admins"):
        with pytest.raises(sa.exc.ProgrammingError):
            with db.begin_nested():
                db.execute(sa.text(stmt))
