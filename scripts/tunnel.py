"""The public site's way to this laptop (spec 2026-10-09 §10).

    PYTHONPATH=. python -m scripts.tunnel

Runs a Cloudflare quick tunnel to the API (no account, no domain), reads the random https://<words>.trycloudflare.com
URL it prints, waits until /health answers through it, then publishes it in `public_endpoints` (row 'api'), where
the console looks it up with the Supabase publishable key. Keeps running; when cloudflared exits this exits too and
the demo supervisor (`scripts.demo watch`) restarts it, which publishes the new URL.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
import urllib.request

import sqlalchemy as sa

URL_RE = re.compile(r"https://([a-z0-9-]+)\.trycloudflare\.com")
API = "http://127.0.0.1:8000"


def parse_url(line: str) -> str | None:
    """The tunnel's own URL from one line of cloudflared output; never Cloudflare's API host."""
    m = URL_RE.search(line)
    return m.group(0) if m and m.group(1) != "api" else None


def publish(c: sa.Connection, url: str) -> None:
    c.execute(sa.text("""insert into public_endpoints (name, url, updated_at) values ('api', :u, now())
                         on conflict (name) do update set url = excluded.url, updated_at = now()"""), {"u": url})


def healthy(url: str, timeout_s: float = 120) -> bool:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(url + "/health", timeout=20) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001 - DNS for a new tunnel takes a few seconds to resolve
            pass
        time.sleep(3)
    return False


def main() -> int:
    from services.api.db import engine
    npx = shutil.which("npx") or "npx"
    cmd = f'"{npx}" -y cloudflared tunnel --no-autoupdate --url {API}'
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                         encoding="utf-8", errors="replace")
    published = False
    assert p.stdout is not None
    for line in p.stdout:
        print(line, end="", flush=True)
        url = None if published else parse_url(line)
        if not url:
            continue
        while not healthy(url):  # the API may be restarting: keep trying this URL rather than give up on it
            print(f"tunnel: {url} not answering /health yet; retrying", flush=True)
        for attempt in range(1, 6):
            try:
                with engine().begin() as c:
                    publish(c, url)
                print(f"tunnel: published {url}", flush=True)
                published = True
                break
            except Exception as e:  # noqa: BLE001 - home-network DNS blips: retry, never die over it
                print(f"tunnel: publish attempt {attempt} failed: {type(e).__name__}", flush=True)
                time.sleep(5 * attempt)
    return p.wait()


if __name__ == "__main__":
    sys.exit(main())
