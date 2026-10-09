"""The console works whichever way this machine is spelled in the address bar (localhost or 127.0.0.1), on any local
port (dev server, preview, e2e), and from the hosted console origins listed in CONSOLE_ORIGINS (env or .env)."""
import os

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient


def _allowed(app: FastAPI, origin: str) -> bool:
    r = TestClient(app).options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    return r.headers.get("access-control-allow-origin") == origin


def _app(origins: str) -> FastAPI:
    from services.api.main import cors_config
    a = FastAPI()
    a.add_middleware(CORSMiddleware, **cors_config(origins))
    a.get("/health")(lambda: {"status": "ok"})
    return a


@pytest.mark.parametrize("origin", ["http://localhost:5180", "http://127.0.0.1:5180"])
def test_default_cors_allows_both_spellings_of_the_console_origin(origin, monkeypatch):
    if os.environ.get("CONSOLE_ORIGINS"):
        pytest.skip("CONSOLE_ORIGINS is set explicitly in this environment")
    from services.api.main import app
    assert _allowed(app, origin)


@pytest.mark.parametrize("origin", ["http://localhost:4173", "http://127.0.0.1:5181", "http://localhost"])
def test_any_local_port_is_allowed(origin):
    assert _allowed(_app(""), origin)


@pytest.mark.parametrize("origin", ["https://evil.example", "http://localhost.evil.example",
                                    "http://127.0.0.1.evil.example:5180", "https://q-cert-chain.vercel.app"])
def test_other_origins_are_refused_unless_listed(origin):
    assert not _allowed(_app(""), origin)


def test_listed_hosted_origin_is_allowed():
    app = _app("https://q-cert-chain.vercel.app")
    assert _allowed(app, "https://q-cert-chain.vercel.app")
    assert not _allowed(app, "https://other.vercel.app")


def test_console_origins_come_from_the_env_file(tmp_path, monkeypatch):
    from services.config import load_settings
    monkeypatch.delenv("CONSOLE_ORIGINS", raising=False)
    f = tmp_path / ".env"
    f.write_text("CONSOLE_ORIGINS=https://q-cert-chain.vercel.app\n", encoding="utf-8")
    assert load_settings(f).console_origins == "https://q-cert-chain.vercel.app"


def test_the_hosted_console_is_allowed_by_default():
    """The public site must not depend on one line of a local .env (it was lost once, 2026-10-10)."""
    from services.config import Settings
    assert "https://q-cert-chain.vercel.app" in Settings().console_origins.split(",")
