import json

import httpx

from services.ml.brand_refs import collect, load_brand_favicons


async def test_collects_favicon_hash_per_brand_and_skips_failures(tmp_path):
    def handler(req):
        if req.url.host == "sbi.co.in" and req.url.path == "/":
            return httpx.Response(200, text='<link rel="shortcut icon" href="/img/fav.ico">')
        if req.url.host == "sbi.co.in" and req.url.path == "/img/fav.ico":
            return httpx.Response(200, content=b"SBI-ICON")
        raise httpx.ConnectError("down")
    brands = [("State Bank of India", ["sbi.co.in"]), ("HDFC Bank", ["hdfcbank.com"])]
    out = await collect(brands, transport=httpx.MockTransport(handler))
    from services.enrich.fingerprint import favicon_hash
    assert out["State Bank of India"] == [favicon_hash(b"SBI-ICON")]
    assert "HDFC Bank" not in out  # unreachable brand: absent, never a guessed hash
    p = tmp_path / "f.json"
    p.write_text(json.dumps(out))
    assert load_brand_favicons(p) == {"State Bank of India": {favicon_hash(b"SBI-ICON")}}


def test_missing_file_means_no_favicon_signal(tmp_path):
    assert load_brand_favicons(tmp_path / "missing.json") == {}


async def test_every_declared_icon_is_a_reference(tmp_path):
    """B1: kits copy whichever icon they scraped (PNG, apple-touch, /favicon.ico); one hash per brand misses them."""
    page = ('<link rel="icon" type="image/png" href="/i/32.png"><link rel="apple-touch-icon" href="/i/180.png">'
            '<link rel="stylesheet" href="/s.css">')
    files = {"/": page, "/i/32.png": b"PNG32", "/i/180.png": b"PNG180", "/favicon.ico": b"ICO"}

    def handler(req):
        if req.url.host == "meesho.com" and req.url.path in files:
            body = files[req.url.path]
            return httpx.Response(200, text=body) if isinstance(body, str) else httpx.Response(200, content=body)
        return httpx.Response(404)
    out = await collect([("Meesho", ["meesho.com"])], transport=httpx.MockTransport(handler))
    from services.enrich.fingerprint import favicon_hash
    assert out["Meesho"] == sorted({favicon_hash(b) for b in (b"PNG32", b"PNG180", b"ICO")})


async def test_inline_data_uri_icon_is_skipped_not_fatal():
    page = '<link rel="icon" href="data:image/vnd.microsoft.icon;base64,AAAB">'

    def handler(req):
        if req.url.path == "/":
            return httpx.Response(200, text=page)
        if req.url.path == "/favicon.ico":
            return httpx.Response(200, content=b"ICO")
        return httpx.Response(404)
    out = await collect([("Yes Bank", ["yesbank.in"])], transport=httpx.MockTransport(handler))
    from services.enrich.fingerprint import favicon_hash
    assert out["Yes Bank"] == [favicon_hash(b"ICO")]
