"""The console works whichever way this machine is spelled in the address bar (localhost or 127.0.0.1)."""
import os

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("origin", ["http://localhost:5180", "http://127.0.0.1:5180"])
def test_default_cors_allows_both_spellings_of_the_console_origin(origin, monkeypatch):
    if os.environ.get("CONSOLE_ORIGINS"):
        pytest.skip("CONSOLE_ORIGINS is set explicitly in this environment")
    from services.api.main import app
    r = TestClient(app).options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == origin
