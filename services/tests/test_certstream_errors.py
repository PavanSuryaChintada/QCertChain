"""B3: the aggregator's per-operator fetch errors, parsed from certstream-server-go's log (no guessing the cause)."""
from scripts.certstream_errors import parse

LOG = """2026/10/07 23:59:37 ct-tiled.go:276: Error processing tiled log updates for 'https://tuscolo2027h2.skylight.geomys.org': fetching checkpoint: failed to execute checkpoint request: Get "https://tuscolo2027h2.skylight.geomys.org/checkpoint": EOF
2026/10/07 23:59:38 ct-tiled.go:276: Error processing tiled log updates for 'https://tuscolo2027h2.skylight.geomys.org': fetching checkpoint: Get "x": context deadline exceeded
2026/10/07 23:59:39 ct-tiled.go:276: Error processing tiled log updates for 'https://halloumi2027h1.log.ipng.ch': fetching checkpoint: Get "x": net/http: request canceled (Client.Timeout exceeded while awaiting headers)
2026/10/07 23:59:40 ct-watcher.go:380: Starting worker for CT log: https://tuscolo2027h2.skylight.geomys.org
"""


def test_errors_are_counted_per_operator_and_cause():
    out = parse(LOG.splitlines())
    assert out["errors_by_operator"] == {"geomys.org": 2, "ipng.ch": 1}
    assert out["causes_by_operator"]["geomys.org"] == {"connection closed by the server (EOF)": 1, "timeout": 1}
    assert out["causes_by_operator"]["ipng.ch"] == {"timeout": 1}
