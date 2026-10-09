"""Stand up the WHOLE demo on local services only and run the browser click-through (A6 + A7).

No Supabase and no internet: a local Postgres database (its own: `<test db>_e2e`), local Redis, a local Hardhat chain
with the contracts deployed, the API and the anchor worker, and the built console served by `vite preview`. Then:
reset the demo, publish Bank One's campaign to the chain, wait for the anchors, and run e2e/test_demo_path.py, which
also aborts every non-localhost request in the browser.

    python -m scripts.e2e_stack            (CI: the e2e job; locally: Docker Postgres + Redis + `npx hardhat node`)
Env: TEST_DATABASE_URL, REDIS_URL, CHAIN_RPC, ORG_PRIVATE_KEY, ORG2_PRIVATE_KEY (Hardhat accounts #1/#2).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import nacl.signing
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parent.parent
API_PORT, CONSOLE_PORT = 8100, 4173
API = f"http://127.0.0.1:{API_PORT}"
CONSOLE = f"http://127.0.0.1:{CONSOLE_PORT}"
PY = sys.executable


def _http(method: str, path: str, key: str, timeout: float = 1500):
    req = urllib.request.Request(API + path, method=method, headers={"X-API-Key": key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _wait(url: str, seconds: float, label: str) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            urllib.request.urlopen(url, timeout=5)
            return
        except Exception:
            time.sleep(1)
    raise SystemExit(f"{label} did not come up at {url} within {seconds:.0f} s")


def _database(base_url: str) -> str:
    """A dedicated database next to the test database, recreated from scratch (never Supabase)."""
    assert "supabase" not in base_url, "the e2e stack never touches the hosted database"
    url = base_url.rsplit("/", 1)[0] + "/" + base_url.rsplit("/", 1)[1].split("?")[0] + "_e2e"
    admin = sa.create_engine(base_url, isolation_level="AUTOCOMMIT")
    name = url.rsplit("/", 1)[1]
    with admin.connect() as c:
        c.exec_driver_sql(f'drop database if exists "{name}" with (force)')
        c.exec_driver_sql(f'create database "{name}"')
    admin.dispose()
    from scripts.apply_schema import apply
    apply(url)
    return url


def main() -> int:
    from services.api import auth
    from services.config import SETTINGS
    t_start = time.monotonic()
    db_url = _database(os.environ.get("TEST_DATABASE_URL", SETTINGS.test_database_url))
    eng = sa.create_engine(db_url)
    with eng.begin() as c:
        keys = {"org1": auth.create_key(c, "org", "org1", "e2e"), "org2": auth.create_key(c, "org", "org2", "e2e"),
                "demo": auth.create_key(c, "demo", "org1", "e2e"), "admin": auth.create_key(c, "admin", None, "e2e")}
    eng.dispose()
    evidence = tempfile.mkdtemp(prefix="qcc-e2e-evidence-")
    env = {**os.environ, "DATABASE_URL": db_url, "EVIDENCE_DIR": evidence,
           "COLLECTOR_PRIVATE_KEY": nacl.signing.SigningKey.generate().encode().hex(),
           "CONSOLE_ORIGINS": f"{CONSOLE},http://localhost:{CONSOLE_PORT}", "API_REGION": "local",
           "RATE_LIMIT_DEMO": "60", "PYTHONUNBUFFERED": "1"}
    procs: list[subprocess.Popen] = []
    logs = ROOT / "e2e" / "artifacts"
    logs.mkdir(parents=True, exist_ok=True)

    def start(args, name, cwd=ROOT, extra=None):
        f = open(logs / f"{name}.log", "w", encoding="utf-8")
        procs.append(subprocess.Popen(args, cwd=cwd, env={**env, **(extra or {})}, stdout=f, stderr=subprocess.STDOUT,
                                      shell=isinstance(args, str)))

    try:
        start([PY, "-m", "uvicorn", "services.api.main:app", "--port", str(API_PORT)], "api")
        start([PY, "-m", "services.api.workers.anchor_worker"], "anchor")
        _wait(API + "/health", 120, "API")
        t = time.monotonic()
        seeded = _http("POST", "/admin/reset", keys["admin"])
        print(f"reset demo: {seeded['seeded']} in {time.monotonic() - t:.0f} s", flush=True)
        o1 = seeded["seeded"]["org1"]["campaign_id"]
        _http("POST", f"/ledger/publish/{o1}", keys["org1"])
        end = time.monotonic() + 600
        while time.monotonic() < end and not _http("GET", f"/campaigns/{o1}", keys["org1"])["anchored"]:
            time.sleep(3)
        print(f"published and anchored: {_http('GET', f'/campaigns/{o1}', keys['org1'])['anchored']}", flush=True)

        npm = shutil.which("npm") or "npm"
        console = ROOT / "apps" / "console"
        # its own output folder: never overwrite a demo build in dist/ that is pointed at the real API
        b = subprocess.run(f'"{npm}" run build -- --outDir dist-e2e --emptyOutDir', cwd=console, shell=True,
                           env={**env, "VITE_API_URL": API},
                           capture_output=True, text=True)
        if b.returncode:
            print(b.stdout[-3000:], b.stderr[-3000:])
            return 2
        # the built console is static: serve dist/ with a stdlib server (SPA fallback to index.html). `vite preview`
        # needs esbuild at start-up, which proved flaky on Windows; this has no moving parts.
        start([PY, "-m", "scripts.e2e_stack", "--serve", str(console / "dist-e2e"), str(CONSOLE_PORT)], "console")
        _wait(CONSOLE, 60, "console")

        test_env = {**env, "E2E_CONSOLE_URL": CONSOLE, "E2E_API_URL": API, "E2E_ARTIFACTS": str(logs),
                    **{f"E2E_KEY_{k.upper()}": v for k, v in keys.items()}}
        t = time.monotonic()
        r = subprocess.run([PY, "-m", "pytest", "e2e/test_demo_path.py", "e2e/test_tour.py", "-q", "-s", "-p", "no:cacheprovider",
                            "-m", "e2e"], cwd=ROOT, env=test_env)
        print(f"e2e: exit {r.returncode}; click-through {time.monotonic() - t:.0f} s; "
              f"whole stack {time.monotonic() - t_start:.0f} s", flush=True)
        return r.returncode
    finally:
        for p in procs:
            if os.name == "nt":
                subprocess.run(f"taskkill /F /T /PID {p.pid}", shell=True, capture_output=True)
            else:
                p.terminate()


def serve(root: str, port: int) -> None:
    """Static file server for the built console, with the single-page-app fallback."""
    import functools
    import http.server

    class SPA(http.server.SimpleHTTPRequestHandler):
        def send_head(self):
            path = Path(self.translate_path(self.path))
            if not path.exists() or (path.is_dir() and not (path / "index.html").exists()):
                self.path = "/index.html"
            return super().send_head()

        def log_message(self, fmt, *args):
            pass
    import socket
    import threading
    handler = functools.partial(SPA, directory=root)

    class V6(http.server.ThreadingHTTPServer):
        address_family = socket.AF_INET6

    # loopback only, on BOTH families: a browser opening "localhost" tries ::1 first, and an IPv4-only server costs
    # ~200 ms per connection on Windows. If IPv6 loopback is unavailable, IPv4 alone still serves.
    try:
        threading.Thread(target=V6(("::1", port), handler).serve_forever, daemon=True).start()
    except OSError:
        pass
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--serve":
        serve(sys.argv[2], int(sys.argv[3]))
    else:
        raise SystemExit(main())
