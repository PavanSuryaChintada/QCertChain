# CT capture report — 2026-10-06 13:28–13:58 UTC (30.6 min)

- Server processed **1,265,158** log entries (689/s). The capture client received **920,052** messages (501/s) = **401,426 unique certificates** (219/s); 56.4% of messages are the same certificate delivered from another log (the server does not dedup across logs; our ingest does).
- **345,106 entries (27.3%) were processed by the server but not delivered to the capture client.** Most likely dropped for a slow client (per-client buffer 300; the full stream carried DER + chain, 7.8 GB). The server exposes no drop counter, so the cause is inferred, not measured. Live ingest uses the lite stream; the delivered/processed ratio is re-measured there.
- Tiled (static-ct) logs supplied **37.4%** of entries.
- Capture client reconnects: 1 (keepalive timeout, 5 s gap).

| Operator | Entries | Share | Tiled entries | Logs | Logs with 0 entries |
|---|---:|---:|---:|---:|---|
| Sectigo | 378,129 | 29.9% | 0 | 8 | mammoth2026h2.ct.sectigo.com, sabre2026h2.ct.sectigo.com |
| Google | 279,766 | 22.1% | 127,566 | 10 | — |
| TrustAsia | 137,651 | 10.9% | 52,224 | 4 | — |
| Let's Encrypt | 120,169 | 9.5% | 120,169 | 6 | — |
| IPng Networks | 106,399 | 8.4% | 106,399 | 10 | halloumi2028h1.mon.ct.ipng.ch |
| Cloudflare | 97,132 | 7.7% | 0 | 2 | ct.cloudflare.com/logs/nimbus2026 |
| DigiCert | 79,604 | 6.3% | 0 | 6 | — |
| Geomys | 65,324 | 5.2% | 65,324 | 10 | — |
| Microsec | 984 | 0.1% | 984 | 5 | — |
| GoDaddy | 0 | 0.0% | 0 | 5 | ct-log-api.godaddy.com/aquamarine2026h2, ct-log-api.godaddy.com/aquamarine2027h1, ct-log-api.godaddy.com/aquamarine2027h2, ct-log-api.godaddy.com/aquamarine2028h1, ct-log-api.godaddy.com/aquamarine2028h2 |

## Outbound load on CT log operators

- Measured inbound from CT logs: 3.40 GB (14.8 Mbit/s).
- Derived requests: 1,870 tile + 3,107 get-entries + 4,531–33,984 checkpoint polls = **5.18–21.21 req/s** across all operators.
- certstream-server-go exposes no HTTP request counter. Requests are derived: one full data tile per 256 tiled entries (partial tiles deferred up to 60 s, #104 fix); one get-entries per 256 RFC 6962 entries; one checkpoint poll per tiled log every 2-15 s. Inbound bytes are measured (docker stats RX of the certstream container).

## Follow-up: lite stream delivery (2026-10-06, 120 s)

Server processed 171,038 entries; a receive-only client on the lite stream (`/`, no DER/chain) got 158,727 → **92.8 % delivered** (vs 72.7 % on the full stream during the capture). 1,283 msg/s. Metric snapshots are cached 5 s by the server, so the ratio is ±~2 %. Re-measured with the real ingest consumer in Task 26.

## excluded_logs

**None proposed.** Owner rule: no trimming without measured per-operator volume. Let's Encrypt's tiled logs (all 6 delivering) carry the DV certificates that matter most for phishing and for the CT-vs-OpenPhish lead-time metric; Google (45.6 % tiled) and TrustAsia also deliver tiled entries. Coverage gaps are involuntary, not trimming: GoDaddy (5 logs, HTTP 429 at startup → workers removed), Cloudflare nimbus2026, Sectigo mammoth2026h2 / sabre2026h2, IPng halloumi2028h1 (0 entries in the window).
