"""Why live candidates do not confirm (B1): the unreachable breakdown by cause, its concentration by site, and the
strong-signal census. Read-only against the live database.

    PYTHONPATH=. python -m scripts.diagnose_confirm [--org 1] [--since 2026-10-07T06:30:36Z] [--out reports/confirm_diagnosis.json]

Causes come from the stored verdict detail (services/enrich/confirm.py and fetch.py). Rows written before the
2026-10-07 fix labelled a DNS failure as "resolves to a non-public address"; those names are RE-RESOLVED now and
split into dns / non-public, which the output says (`relabelled_at_diagnosis`).
"""
from __future__ import annotations

import argparse
import json
import re
import socket
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa

from services.config import ROOT, SETTINGS
from services.enrich.fetch import is_public_ip
from services.ingest.brands import etld1

RULES = (  # (cause, regex on the stored detail), first match wins
    ("hosting provider phishing interstitial", r"interstitial"),
    ("dns: name does not resolve", r"^could not fetch: dns:"),
    ("ssrf guard: non-public address", r"non-public address"),
    ("timeout", r"Timeout|timed out|TimeoutError"),
    ("tls / http protocol error", r"ERR_SSL|ERR_HTTP2|SSL|ProtocolError|ERR_CERT"),
    ("redirect loop", r"redirect|ERR_TOO_MANY_REDIRECTS"),
    ("dns: name does not resolve", r"getaddrinfo failed|ERR_NAME_NOT_RESOLVED"),
    ("connection refused / reset", r"ConnectError|ERR_CONNECTION|refused|reset"),
    ("response too large", r"too large|cap"),
)


def cause(detail: str) -> str:
    m = re.match(r"HTTP (\d+); parked or error page", detail)
    if m:
        code = int(m.group(1))
        return "parked page (HTTP 2xx/3xx)" if code < 400 else f"HTTP {code // 100}xx error page ({code})" \
            if code not in (401, 403, 404) else f"HTTP {code} error page"
    for name, rx in RULES:
        if re.search(rx, detail):
            return name
    return "other: " + detail[:60]


def _resolves_public(host: str) -> str:
    try:
        ips = {i[4][0] for i in socket.getaddrinfo(host, 443)}
    except OSError:
        return "dns: name does not resolve"
    return "ssrf guard: non-public address" if not all(is_public_ip(i) for i in ips) else \
        "resolves publicly now (was not, or DNS changed)"


def diagnose(conn: sa.Connection, org: int, since: str | None) -> dict:
    rows = conn.execute(sa.text("""
        select d.name, v.status, coalesce(v.confirm_reasons->'signals'->0->>'detail', '') detail,
               coalesce(public.strong_signal_count(v.confirm_reasons), 0) strong
        from domain_verdicts v join domains d on d.id = v.domain_id
        where v.org_id = :o and d.source <> 'seed' and (cast(:since as timestamptz) is null or v.verdict_at >= cast(:since as timestamptz))
    """), {"o": org, "since": since}).all()
    unr = [r for r in rows if r.status == "unreachable"]
    causes, relabelled = Counter(), Counter()
    for r in unr:
        c = cause(r.detail)
        if c == "ssrf guard: non-public address" and "dns:" not in r.detail:
            c2 = _resolves_public(r.name)
            relabelled[c2] += 1
            c = c2
        causes[c] += 1
    sites = Counter(etld1(r.name) for r in unr)
    top_site, top_n = sites.most_common(1)[0] if sites else ("", 0)
    return {
        "dataset": "domain_verdicts (live, source <> 'seed')", "org_id": org, "since": since,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "verdicts": dict(Counter(r.status for r in rows)),
        "with_at_least_one_strong_signal": sum(r.strong >= 1 for r in rows),
        "unreachable": {"n": len(unr), "by_cause": dict(causes.most_common()),
                        "relabelled_at_diagnosis": dict(relabelled),
                        "distinct_sites": len(sites), "top_sites": sites.most_common(5),
                        "excluding_top_site": {"site": top_site, "n": len(unr) - top_n}},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--org", type=int, default=1)
    ap.add_argument("--since")
    ap.add_argument("--out", default=str(ROOT / "reports/confirm_diagnosis.json"))
    a = ap.parse_args()
    with sa.create_engine(SETTINGS.database_url).connect() as c:
        out = diagnose(c, a.org, a.since)
    Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
