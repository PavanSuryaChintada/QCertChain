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
