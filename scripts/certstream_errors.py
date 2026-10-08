"""Per-operator fetch errors of the self-hosted CT aggregator (certstream-server-go), from its own log.

    docker logs qcertchain-certstream-1 > .superpowers/certstream_container.log 2>&1
    PYTHONPATH=. python -m scripts.certstream_errors [--log .superpowers/certstream_container.log]

Explains per-operator coverage (B3) with measured causes: every "Error processing ... log updates for '<log url>'"
line is counted against the log's operator (registrable domain) and classified by its error text.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from services.config import ROOT

_LINE = re.compile(r"Error processing .*? for 'https?://([^/']+)")
CAUSES = (  # first match wins
    ("connection closed by the server (EOF)", re.compile(r":\s*EOF\s*$|unexpected EOF")),
    ("timeout", re.compile(r"Client\.Timeout|context deadline exceeded|i/o timeout|TLS handshake timeout")),
    ("DNS failure", re.compile(r"no such host")),
    ("connection reset or refused", re.compile(r"connection reset|connection refused")),
    ("HTTP error status", re.compile(r"status code \d+|\b(429|5\d\d)\b")),
)


def _operator(host: str) -> str:
    parts = host.lower().split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def parse(lines) -> dict:
    by_op: Counter = Counter()
    causes: dict[str, Counter] = defaultdict(Counter)
    for line in lines:
        m = _LINE.search(line)
        if not m:
            continue
        op = _operator(m.group(1))
        by_op[op] += 1
        cause = next((name for name, rx in CAUSES if rx.search(line)), "other")
        causes[op][cause] += 1
    return {"errors_by_operator": dict(by_op.most_common()),
            "causes_by_operator": {op: dict(c.most_common()) for op, c in causes.items()}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--log", default=str(ROOT / ".superpowers/certstream_container.log"))
    a = ap.parse_args()
    print(json.dumps(parse(Path(a.log).read_text(encoding="utf-8", errors="replace").splitlines()), indent=1))


if __name__ == "__main__":
    main()
