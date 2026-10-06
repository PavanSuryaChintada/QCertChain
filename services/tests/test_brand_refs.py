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
