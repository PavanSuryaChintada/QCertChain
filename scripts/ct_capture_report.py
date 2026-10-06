"""Per-operator CT volume, tiled-log share and outbound request estimate for the 30-minute capture.

Inputs (written by the capture run): reports/ct_capture/{metrics_start,metrics_end}.txt (certstream-server-go
Prometheus snapshots), {start,end}_time.txt, {netio_start,netio_end}.txt (docker stats), capture.log.
Output: reports/ct_capture/report.json and report.md. Request counts are DERIVED, not measured: the server
exposes no HTTP request counter (see method notes in the output).
"""
import json
import math
import re
from collections import defaultdict
from datetime import datetime

import httpx

from services.config import ROOT

D = ROOT / "reports/ct_capture"
LINE = re.compile(r'certstreamservergo_certs_by_log_total\{url="([^"]+)",operator="([^"]+)"\} (\d+)')
TILE = 256                      # static-ct-api data tile width
RFC_BATCH = 256                 # certstream-server-go v1.10 get-entries batch size (#97)
CHECKPOINT_POLL_S = (2, 15)     # tiled checkpoint backoff min/max (ct-tiled.go)


def snap(name):
    out = {}
    for url, op, n in LINE.findall((D / name).read_text(encoding="utf-8")):
        out[url.rstrip("/")] = (op, int(n))
    return out


def to_bytes(s):
    num, unit = re.match(r"([\d.]+)\s*([kMG]?B)", s).groups()
    return float(num) * {"B": 1, "kB": 1e3, "MB": 1e6, "GB": 1e9}[unit]


start, end = snap("metrics_start.txt"), snap("metrics_end.txt")
t0 = datetime.fromisoformat((D / "start_time.txt").read_text().strip().replace("Z", "+00:00"))
t1 = datetime.fromisoformat((D / "end_time.txt").read_text().strip().replace("Z", "+00:00"))
secs = (t1 - t0).total_seconds()

loglist = httpx.get("https://www.gstatic.com/ct/log_list/v3/all_logs_list.json", timeout=30).json()
kind = {}
for op in loglist["operators"]:
    for lg in op.get("logs", []):
        kind[lg["url"].split("://", 1)[1].rstrip("/")] = "rfc6962"
    for lg in op.get("tiled_logs", []):
        for k in ("monitoring_url", "submission_url"):
            if lg.get(k):
                kind[lg[k].split("://", 1)[1].rstrip("/")] = "tiled"

per_log, per_op = [], defaultdict(lambda: {"entries": 0, "logs": 0, "tiled_entries": 0, "zero_logs": []})
for url, (op, n_end) in sorted(end.items()):
    delta = n_end - start.get(url, (op, 0))[1]
    k = kind.get(url, "unknown")
    per_log.append({"url": url, "operator": op, "type": k, "entries": delta, "per_sec": round(delta / secs, 2)})
    o = per_op[op]
    o["entries"] += delta
    o["logs"] += 1
    if k == "tiled":
        o["tiled_entries"] += delta
    if delta == 0:
        o["zero_logs"].append(url)

total = sum(x["entries"] for x in per_log)
tiled_total = sum(x["entries"] for x in per_log if x["type"] == "tiled")
captured, fps, by_type = 0, set(), defaultdict(int)
with open(ROOT / "data/capture.jsonl", encoding="utf-8") as fh:
    for line in fh:
        m = json.loads(line)
        captured += 1
        fps.add(m["data"]["leaf_cert"].get("sha256"))
        by_type[(m["data"].get("source") or {}).get("type")] += 1
unique = len(fps)
n_tiled_logs = sum(1 for x in per_log if x["type"] == "tiled" and x["entries"] > 0)
n_rfc_logs = sum(1 for x in per_log if x["type"] == "rfc6962" and x["entries"] > 0)
tile_req = sum(math.ceil(x["entries"] / TILE) for x in per_log if x["type"] == "tiled")
rfc_req = sum(math.ceil(x["entries"] / RFC_BATCH) for x in per_log if x["type"] == "rfc6962")
ckpt_lo = n_tiled_logs * secs / CHECKPOINT_POLL_S[1]
ckpt_hi = n_tiled_logs * secs / CHECKPOINT_POLL_S[0]
rx = to_bytes((D / "netio_end.txt").read_text().split("/")[0]) - to_bytes((D / "netio_start.txt").read_text().split("/")[0])
log_text = (D / "capture.log").read_text(encoding="utf-8")

report = {
    "window_utc": [t0.isoformat(), t1.isoformat()], "seconds": round(secs),
    "server_entries_processed": total, "server_entries_per_sec": round(total / secs, 1),
    "captured_messages": captured, "captured_per_sec": round(captured / secs, 1),
    "captured_unique_certs": unique, "unique_certs_per_sec": round(unique / secs, 1),
    "duplicate_delivery_share": round(1 - unique / captured, 4),
    "undelivered_to_capture_client": total - captured,
    "undelivered_share": round(1 - captured / total, 4),
    "captured_by_log_type": dict(by_type),
    "capture_reconnects": log_text.count("connection issue"),
    "tiled_share_of_entries": round(tiled_total / total, 4) if total else None,
    "per_operator": {op: {**v, "share": round(v["entries"] / total, 4)} for op, v in
                     sorted(per_op.items(), key=lambda kv: -kv[1]["entries"])},
    "per_log": sorted(per_log, key=lambda x: -x["entries"]),
    "outbound": {
        "inbound_bytes_from_ct_logs": int(rx), "inbound_mbit_per_sec": round(rx * 8 / secs / 1e6, 2),
        "derived_tile_requests": tile_req, "derived_rfc6962_get_entries_requests": rfc_req,
        "derived_checkpoint_polls_range": [round(ckpt_lo), round(ckpt_hi)],
        "derived_total_requests_per_sec_range": [round((tile_req + rfc_req + ckpt_lo) / secs, 2),
                                                 round((tile_req + rfc_req + ckpt_hi) / secs, 2)],
        "method": ("certstream-server-go exposes no HTTP request counter. Requests are derived: one "
                   "full data tile per 256 tiled entries (partial tiles deferred up to 60 s, #104 fix); one "
                   "get-entries per 256 RFC 6962 entries; one checkpoint poll per tiled log every 2-15 s. "
                   "Inbound bytes are measured (docker stats RX of the certstream container)."),
    },
}
(D / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")

md = [f"# CT capture report — {t0:%Y-%m-%d %H:%M}–{t1:%H:%M} UTC ({secs / 60:.1f} min)", "",
      f"- Server processed **{total:,}** log entries ({total / secs:.0f}/s). The capture client received "
      f"**{captured:,}** messages ({captured / secs:.0f}/s) = **{unique:,} unique certificates** ({unique / secs:.0f}/s); "
      f"{1 - unique / captured:.1%} of messages are the same certificate delivered from another log "
      "(the server does not dedup across logs; our ingest does).",
      f"- **{total - captured:,} entries ({1 - captured / total:.1%}) were processed by the server but not delivered "
      "to the capture client.** Most likely dropped for a slow client (per-client buffer 300; the full stream "
      "carried DER + chain, 7.8 GB). The server exposes no drop counter, so the cause is inferred, not measured. "
      "Live ingest uses the lite stream; the delivered/processed ratio is re-measured there.",
      f"- Tiled (static-ct) logs supplied **{tiled_total / total:.1%}** of entries.",
      f"- Capture client reconnects: {report['capture_reconnects']} (keepalive timeout, 5 s gap).", "",
      "| Operator | Entries | Share | Tiled entries | Logs | Logs with 0 entries |", "|---|---:|---:|---:|---:|---|"]
for op, v in report["per_operator"].items():
    md.append(f"| {op} | {v['entries']:,} | {v['share']:.1%} | {v['tiled_entries']:,} | {v['logs']} | "
              f"{', '.join(v['zero_logs']) or '—'} |")
o = report["outbound"]
md += ["", "## Outbound load on CT log operators", "",
       f"- Measured inbound from CT logs: {o['inbound_bytes_from_ct_logs'] / 1e9:.2f} GB ({o['inbound_mbit_per_sec']} Mbit/s).",
       f"- Derived requests: {o['derived_tile_requests']:,} tile + {o['derived_rfc6962_get_entries_requests']:,} get-entries "
       f"+ {o['derived_checkpoint_polls_range'][0]:,}–{o['derived_checkpoint_polls_range'][1]:,} checkpoint polls "
       f"= **{o['derived_total_requests_per_sec_range'][0]}–{o['derived_total_requests_per_sec_range'][1]} req/s** across all operators.",
       f"- {o['method']}"]
(D / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print("\n".join(md))
