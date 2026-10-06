import httpx
import pytest

from services.enrich.fetch import FetchedPage, RateLimited, Unreachable, fetch_httpx


def transport(routes):
    def handler(req: httpx.Request):
        h = routes.get(str(req.url))
        if h is None:
            return httpx.Response(404, text="nope")
        return h(req) if callable(h) else h
    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def fake_public_dns(monkeypatch):
    """MockTransport tests must not touch real DNS: every host resolves to a public documentation-adjacent
    address unless a test passes its own resolver."""
    async def resolve(host):
        return ["93.184.216.34"]
    monkeypatch.setattr("services.enrich.fetch.resolve_host", resolve)

async def test_httpx_fetch_follows_redirect_and_records_chain():
    t = transport({
        "https://a.top/": httpx.Response(302, headers={"location": "https://a.top/login"}),
        "https://a.top/login": httpx.Response(200, text="<title>x</title><link rel=icon href=/f.ico>"),
        "https://a.top/f.ico": httpx.Response(200, content=b"ICO"),
    })
    p = await fetch_httpx("a.top", timeout_s=5, user_agent="UA", transport=t)
    assert isinstance(p, FetchedPage) and p.final_url == "https://a.top/login" and p.status == 200
    assert p.redirect_chain == ["https://a.top/"] and p.favicon == b"ICO" and p.via == "httpx"


async def test_redirect_loop_capped_unreachable():
    t = transport({"https://a.top/": httpx.Response(302, headers={"location": "https://a.top/"})})
    r = await fetch_httpx("a.top", timeout_s=5, user_agent="UA", transport=t)
    assert isinstance(r, Unreachable) and "redirect" in r.reason


async def test_connection_error_unreachable():
    def boom(req):
        raise httpx.ConnectError("refused")
    r = await fetch_httpx("a.top", timeout_s=5, user_agent="UA", transport=transport({"https://a.top/": boom}))
    assert isinstance(r, Unreachable)


async def test_user_agent_identifies_scanner():
    seen = {}

    def h(req):
        seen["ua"] = req.headers["user-agent"]
        return httpx.Response(200, text="ok")
    await fetch_httpx("a.top", timeout_s=5, user_agent="QCertChain-Scanner/0.1", transport=transport({"https://a.top/": h}))
    assert seen["ua"] == "QCertChain-Scanner/0.1"


async def test_rate_limited_host_not_fetched():
    from services.enrich.fetch import fetch
    calls = []

    async def limiter(host):
        return False
    r = await fetch("a.top", timeout_s=5, user_agent="UA", limiter=limiter, use_playwright=False,
                    transport=transport({"https://a.top/": lambda req: calls.append(1) or httpx.Response(200)}))
    assert isinstance(r, RateLimited) and calls == []


async def test_unreachable_site_is_not_fetched_twice(monkeypatch):
    """Playwright reached the network and the site is down: an httpx retry only doubles the wait."""
    from services.enrich import fetch as f
    calls = []

    async def pw(domain, **kw):
        calls.append("playwright")
        return Unreachable("net::ERR_NAME_NOT_RESOLVED")

    async def hx(domain, **kw):
        calls.append("httpx")
        return Unreachable("ConnectError")

    monkeypatch.setattr(f, "fetch_playwright", pw)
    monkeypatch.setattr(f, "fetch_httpx", hx)
    r = await f.fetch("dead.example", timeout_s=5, user_agent="UA")
    assert isinstance(r, Unreachable) and calls == ["playwright"]


async def test_httpx_used_when_playwright_itself_is_broken(monkeypatch):
    from services.enrich import fetch as f
    calls = []

    async def pw(domain, **kw):
        raise RuntimeError("browser executable not found")

    async def hx(domain, **kw):
        calls.append("httpx")
        return Unreachable("x")

    monkeypatch.setattr(f, "fetch_playwright", pw)
    monkeypatch.setattr(f, "fetch_httpx", hx)
    await f.fetch("a.example", timeout_s=5, user_agent="UA")
    assert calls == ["httpx"]


def resolver(table):
    async def resolve(host):
        return table.get(host, ["93.184.216.34"])
    return resolve


async def test_host_resolving_to_private_address_is_never_fetched():
    called = []
    t = transport({"https://evil.example/": lambda req: called.append(1) or httpx.Response(200, text="x")})
    r = await fetch_httpx("evil.example", timeout_s=5, user_agent="UA", transport=t,
                          resolve=resolver({"evil.example": ["10.0.0.5"]}))
    assert isinstance(r, Unreachable) and "non-public" in r.reason and called == []


async def test_redirect_to_metadata_service_is_blocked():
    t = transport({"https://a.example/": httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"}),
                   "http://169.254.169.254/latest/": httpx.Response(200, text="SECRET")})
    r = await fetch_httpx("a.example", timeout_s=5, user_agent="UA", transport=t, resolve=resolver({}))
    assert isinstance(r, Unreachable) and "non-public" in r.reason


async def test_redirect_to_internal_service_name_is_blocked():
    t = transport({"https://a.example/": httpx.Response(302, headers={"location": "http://hardhat:8545/"})})
    r = await fetch_httpx("a.example", timeout_s=5, user_agent="UA", transport=t,
                          resolve=resolver({"hardhat": ["172.18.0.4"]}))
    assert isinstance(r, Unreachable)


async def test_huge_body_is_capped_not_loaded():
    from services.enrich.fetch import MAX_HTML_BYTES
    big = b"<html>" + b"A" * (MAX_HTML_BYTES * 3)
    t = transport({"https://a.example/": httpx.Response(200, content=big)})
    r = await fetch_httpx("a.example", timeout_s=5, user_agent="UA", transport=t, resolve=resolver({}))
    assert isinstance(r, FetchedPage) and len(r.html) <= MAX_HTML_BYTES


def test_public_address_check():
    from services.enrich.fetch import is_public_ip
    assert is_public_ip("93.184.216.34")
    for ip in ("127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254", "::1", "fc00::1", "0.0.0.0"):
        assert not is_public_ip(ip), ip
