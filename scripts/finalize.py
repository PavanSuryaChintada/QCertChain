"""Finalize the 24-hour CT capture in one command (`npm run finalize`): integrity, counts, lead time, fixture, report.

    PYTHONPATH=. python -m scripts.finalize [--allow-partial] [--skip-live] [--out-dir DIR]

Inputs (missing -> exit 2 with the reason; nothing is skipped silently):
  data/replay/ct_live.jsonl.gz      certstream messages written by scripts/record_ct.py (one gzip member per run)
  data/replay/ct_live.sqlite        ct_first_seen (every non-allowlisted name) + openphish (30-min polls)
  .superpowers/record_ct.log        the recorder's log: OpenPhish poll times, restarts
  reports/metrics.json              the measured metrics the new sections are merged into
  DATABASE_URL (.env)               the live pipeline's counts (read-only); --skip-live records "not measured"

Outputs. While the capture is still running (no .summary.json from the final run) everything goes to a PREVIEW
location so the real run tomorrow starts clean:
  partial:  reports/finalize_preview/{metrics.json,REPORT.md}, data/replay/finalize_preview/ct_24h.{jsonl.gz,summary.json}
  complete: reports/metrics.json, docs/REPORT.md, data/replay/ct_24h.jsonl.gz, data/replay/ct_24h.summary.json

Every figure records its dataset, window, n and measured_at. Lead time is never estimated: below 10 CT-first matches
it is stored as "not measured: <reason with the counts>".
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
import tempfile
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_IN = ROOT / "data/replay/ct_live.jsonl.gz"
SQLITE_IN = ROOT / "data/replay/ct_live.sqlite"
LOG_IN = ROOT / ".superpowers/record_ct.log"
METRICS = ROOT / "reports/metrics.json"

REPLAY_SPEED = 360.0
REPLAY_SLEEP_CAP_S = 2.0      # services/ingest/stream.py::_replay caps every inter-arrival sleep at 2 s
POLL_S = 1800                 # scripts/record_ct.py --openphish-every-s default
GAP_S = 300                   # an inter-arrival silence this long is a capture gap (normal max measured: < 60 s)
MIN_CT_FIRST = 10             # below this many CT-first matches lead time is "not measured"
W_QUANTILE = 0.99             # exclusion window after capture start / gap end: p99 of the name re-sighting delay
W_STEP_S = 1800               # ... rounded up to the poll resolution
OPERATORS = (                 # (operator, substring of the log URL or name), first match wins
    ("Google", "googleapis"), ("Google", ".goog"), ("Google", "google"),
    ("Cloudflare", "cloudflare"), ("DigiCert", "digicert"), ("Sectigo", "sectigo"),
    ("Let's Encrypt", "letsencrypt"), ("Let's Encrypt", "let's encrypt"), ("TrustAsia", "trustasia"),
    ("Geomys", "geomys"), ("IPng Networks", "ipng"),
)
NAMED_OPERATORS = ("Google", "Cloudflare", "DigiCert", "Sectigo", "Let's Encrypt", "TrustAsia", "Geomys",
                   "IPng Networks")


class InputError(Exception):
    """A required input is missing or unreadable: finalize exits non-zero with this message."""


def iso(ts: float | None) -> str | None:
    return None if ts is None else datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def quantile(xs: list[float], q: float) -> float | None:
    """Nearest-rank quantile on sorted data (the same convention as scripts/evaluate.py::pct)."""
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))] if xs else None


# ---- reading the fixture ---------------------------------------------------------------------------------------
_GZ = b"\x1f\x8b\x08"


def member_offsets(raw: bytes) -> list[int]:
    """Start offset of every gzip member. record_ct.py opens the file in append mode, so each run adds a member; a run
    killed by a machine restart leaves its member without an end marker, and a plain gzip reader then fails at the
    next member ("invalid block type"). A candidate header counts only if it inflates to the start of a JSON line."""
    out, i = [], raw.find(_GZ)
    while i != -1:
        try:
            if zlib.decompressobj(31).decompress(raw[i:i + 65536], 64).startswith(b"{"):
                out.append(i)
        except zlib.error:
            pass
        i = raw.find(_GZ, i + 1)
    return out


def iter_lines(path: Path, stats: dict):
    """Yield (member, line bytes) across all gzip members, tolerating truncated members and a partial last line."""
    raw = Path(path).read_bytes()
    offs = member_offsets(raw)
    if not offs:
        raise InputError(f"{path}: no readable gzip member")
    stats.update(bytes=len(raw), members=len(offs), members_without_end_marker=0, partial_lines_dropped=0,
                 decode_errors=[])
    for k, start in enumerate(offs):
        end = offs[k + 1] if k + 1 < len(offs) else len(raw)
        d, buf, pos = zlib.decompressobj(31), b"", start
        while pos < end and not d.eof:
            chunk = raw[pos:min(pos + (1 << 20), end)]
            pos += len(chunk)
            try:
                buf += d.decompress(chunk)
            except zlib.error as e:
                stats["decode_errors"].append(f"member {k} at byte {pos}: {e}")
                break
            *lines, buf = buf.split(b"\n")
            for ln in lines:
                if ln.strip():
                    yield k, ln
        if not d.eof:
            stats["members_without_end_marker"] += 1
        if buf.strip():  # an unterminated last line: the run died (or is still writing) mid-line
            stats["partial_lines_dropped"] += 1


def operator_of(source: dict | None) -> str:
    s = source or {}
    hay = f"{s.get('url') or ''} {s.get('name') or ''}".lower()
    for op, needle in OPERATORS:
        if needle in hay:
            return op
    return "Other"


def dedup_key(data: dict) -> str:
    leaf = data.get("leaf_cert") or {}
    fp = leaf.get("sha256") or leaf.get("fingerprint")
    if fp:
        return "fp:" + fp
    return f"ix:{(data.get('source') or {}).get('url')}#{data.get('cert_index')}"


# ---- one pass over the capture ---------------------------------------------------------------------------------
@dataclass
class Scan:
    reader: dict = field(default_factory=dict)
    messages: int = 0
    bad_json: int = 0
    no_seen: int = 0
    by_tag: Counter = field(default_factory=Counter)
    seen: list = field(default_factory=list)              # every message's data.seen (unsorted)
    members: dict = field(default_factory=dict)            # member -> {n, first, last}
    minutes: set = field(default_factory=set)              # epoch minutes with >= 1 message
    op_minutes: dict = field(default_factory=lambda: defaultdict(set))
    op_messages: Counter = field(default_factory=Counter)
    op_logs: dict = field(default_factory=lambda: defaultdict(set))
    dup: Counter = field(default_factory=Counter)
    name_sightings: dict = field(default_factory=dict)     # scored names -> [first, second] seen
    candidates: dict = field(default_factory=dict)
    fixture: dict | None = None


def scan_capture(path: Path, *, threshold: float, fixture_out: Path | None = None, triage_fn=None) -> Scan:
    """Read every message once: dedup counts, coverage minutes, re-sighting delays, triage at `threshold`, and (if
    fixture_out) the sorted, de-duplicated replay fixture."""
    from services.ingest.certparse import parse_message
    if triage_fn is None:
        from services.ingest.triage import triage as triage_fn, warm
        warm()
    s = Scan()
    first_member: dict[str, int] = {}
    first_ix_member: dict[str, int] = {}
    cand_fp: set[str] = set()
    cand_names: set[str] = set()
    triaged: dict[str, bool] = {}
    cand_msgs = cand_msgs_scored = cand_msgs_sample = 0
    tmp = tmpdb = None
    if fixture_out is not None:
        tmp = tempfile.TemporaryDirectory(prefix="qcc_fixture_")
        tmpdb = sqlite3.connect(Path(tmp.name) / "fx.sqlite")
        tmpdb.execute("create table fx (key text primary key, seen real, line blob)")
    try:
        for member, line in iter_lines(path, s.reader):
            try:
                msg = json.loads(line)
                data = msg["data"]
            except (ValueError, KeyError, TypeError):
                s.bad_json += 1
                continue
            s.messages += 1
            tag = msg.get("qcertchain_fixture") or "untagged"
            s.by_tag[tag] += 1
            seen = data.get("seen")
            if not isinstance(seen, (int, float)):
                s.no_seen += 1
                continue
            s.seen.append(float(seen))
            mb = s.members.setdefault(member, {"messages": 0, "first_seen": seen, "last_seen": seen})
            mb["messages"] += 1
            mb["first_seen"], mb["last_seen"] = min(mb["first_seen"], seen), max(mb["last_seen"], seen)
            minute = int(seen // 60)
            s.minutes.add(minute)
            src = data.get("source") or {}
            op = operator_of(src)
            s.op_minutes[op].add(minute)
            s.op_messages[op] += 1
            s.op_logs[op].add(src.get("name") or src.get("url") or "?")
            # duplicates: same certificate (fingerprint), and exact re-delivery (same log + cert_index)
            key = dedup_key(data)
            ix = f"{src.get('url')}#{data.get('cert_index')}"
            if key in first_member:
                s.dup["same_certificate"] += 1
                if first_member[key] != member:
                    s.dup["same_certificate_across_runs"] += 1
            else:
                first_member[key] = member
            if ix in first_ix_member:
                s.dup["same_log_entry_redelivered"] += 1
                if first_ix_member[ix] != member:
                    s.dup["same_log_entry_redelivered_across_runs"] += 1
            else:
                first_ix_member[ix] = member
            # triage with the deployed rules, once per certificate
            rec = parse_message(msg)
            if rec and rec.names:
                if key not in triaged:
                    best = 0.0
                    for n in rec.names:
                        sc = triage_fn(n, issuer=rec.issuer, san_count=rec.san_count).score
                        best = max(best, sc)
                        if sc >= threshold:
                            cand_names.add(n)
                    triaged[key] = best >= threshold
                    if triaged[key]:
                        cand_fp.add(key)
                if triaged[key]:
                    cand_msgs += 1
                    cand_msgs_scored += tag == "scored"
                    cand_msgs_sample += tag == "background_sample"
                if tag == "scored":
                    for n in rec.names:
                        v = s.name_sightings.get(n)
                        if v is None:
                            s.name_sightings[n] = [seen, None]
                        elif seen < v[0]:
                            s.name_sightings[n] = [seen, v[0]]
                        elif v[1] is None or seen < v[1]:
                            v[1] = seen
            if tmpdb is not None:
                tmpdb.execute("insert into fx values (?, ?, ?) on conflict (key) do update set seen = excluded.seen, "
                              "line = excluded.line where excluded.seen < fx.seen",
                              (key, float(seen), zlib.compress(line, 1)))
        s.candidates = {"certificates": len(cand_fp), "unique_names": len(cand_names), "messages": cand_msgs,
                        "messages_scored": cand_msgs_scored, "messages_background_sample": cand_msgs_sample,
                        "unique_certificates_triaged": len(triaged)}
        if tmpdb is not None:
            s.fixture = write_fixture(tmpdb, fixture_out)
    finally:
        if tmpdb is not None:
            tmpdb.close()
            tmp.cleanup()
    return s


def write_fixture(db: sqlite3.Connection, out: Path) -> dict:
    """Write the de-duplicated messages sorted by data.seen; returns counts and the replay-time measurement."""
    import gzip
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")
    n, tags, prev, sleep_s, ordered = 0, Counter(), None, 0.0, True
    with gzip.open(part, "wb", compresslevel=6) as f:
        for seen, line in db.execute("select seen, line from fx order by seen, rowid"):
            raw = zlib.decompress(line)
            f.write(raw.rstrip(b"\n") + b"\n")
            n += 1
            tags[json.loads(raw).get("qcertchain_fixture") or "untagged"] += 1
            if prev is not None:
                ordered &= seen >= prev
                sleep_s += replay_sleep(seen - prev)
            prev = seen
    part.replace(out)
    return {"path": out.relative_to(ROOT).as_posix() if out.is_relative_to(ROOT) else out.as_posix(), "messages": n,
            "kept_scored": tags.get("scored", 0), "kept_background_sample": tags.get("background_sample", 0),
            "sorted_by_seen": ordered, "replay_seconds_at_speed": {str(int(REPLAY_SPEED)): round(sleep_s, 1)}}


def replay_sleep(delta: float, speed: float = REPLAY_SPEED, cap: float = REPLAY_SLEEP_CAP_S) -> float:
    """One inter-arrival sleep exactly as services/ingest/stream.py::_replay computes it."""
    return max(0.0, min(delta / speed, cap)) if speed > 0 else 0.0


def replay_seconds(seen_sorted: list[float], speed: float = REPLAY_SPEED) -> float:
    return sum(replay_sleep(b - a, speed) for a, b in zip(seen_sorted, seen_sorted[1:]))


# ---- gaps, coverage ----------------------------------------------------------------------------------------------
def find_gaps(seen: list[float], min_gap_s: float = GAP_S) -> list[tuple[float, float]]:
    xs = sorted(seen)
    return [(a, b) for a, b in zip(xs, xs[1:]) if b - a >= min_gap_s]


def coverage(minutes: set[int], op_minutes: dict[str, set[int]], start: float, end: float,
             gaps: list[tuple[float, float]] | None = None) -> dict:
    """Coverage = minutes with >= 1 certificate / minutes in the window [floor(start), floor(end)]."""
    m0, m1 = int(start // 60), int(end // 60)
    total = m1 - m0 + 1
    gap_minutes = {m for a, b in (gaps or []) for m in range(int(a // 60) + 1, int(b // 60))}
    in_win = lambda ms: {m for m in ms if m0 <= m <= m1}  # noqa: E731
    out = {"minutes_in_window": total, "minutes_covered": len(in_win(minutes)),
           "pct": round(100 * len(in_win(minutes)) / total, 2) if total else None,
           "minutes_inside_gaps": len(gap_minutes), "per_operator": {}}
    for op in sorted(op_minutes, key=lambda o: (o not in NAMED_OPERATORS, o)):
        cov = in_win(op_minutes[op])
        outside = total - len(gap_minutes)
        out["per_operator"][op] = {
            "minutes_covered": len(cov), "pct": round(100 * len(cov) / total, 2) if total else None,
            "pct_outside_gaps": round(100 * len(cov - gap_minutes) / outside, 2) if outside else None}
    return out


def parse_log(text: str, day0: date) -> dict:
    """Recorder log -> poll times, stats lines, restarts. Stamps are [HH:MM] UTC; the day advances when they wrap."""
    stamp = re.compile(r"^\[(\d\d):(\d\d)\] (.*)$")
    day, last_min = day0, None
    polls, stats_lines, events = [], [], []
    reconnects = poll_failures = 0
    for line in text.splitlines():
        if line.startswith("reconnecting after"):
            reconnects += 1
        if line.startswith("openphish poll failed"):
            poll_failures += 1
        m = stamp.match(line)
        if not m:
            continue
        mins = int(m[1]) * 60 + int(m[2])
        if last_min is not None and mins < last_min - 60:
            day += timedelta(days=1)
        last_min = mins
        t = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() + mins * 60
        events.append(t)
        if "openphish:" in m[3]:
            polls.append(t)
        elif m[3].startswith("{"):
            stats_lines.append(t)
    jumps = sorted(((b - a, a, b) for a, b in zip(events, events[1:])), reverse=True)
    return {"polls": polls, "stats_lines": stats_lines, "reconnects": reconnects, "poll_failures": poll_failures,
            "largest_silence": ({"from": iso(jumps[0][1]), "to": iso(jumps[0][2]), "minutes": round(jumps[0][0] / 60)}
                                if jumps else None)}


def resighting_window(name_sightings: dict, q: float = W_QUANTILE, step: float = W_STEP_S) -> dict:
    """W: how long after a gap (or capture start) a first sighting may still be a RE-sighting of a name first shown
    in the gap. Measured: the delay between a name's first and second sighting, quantile q, rounded up to `step`."""
    delays = [b - a for a, b in name_sightings.values() if b is not None]
    qv = quantile(delays, q)
    w = max(step, math.ceil((qv or 0) / step) * step)
    return {"seconds": w, "quantile": q, "quantile_value_s": round(qv, 1) if qv is not None else None,
            "n_names_seen_twice": len(delays), "rounded_up_to_s": step,
            "derivation": f"p{int(q * 100)} of the delay between the first and second sighting of a name in scored "
                          f"certificates ({len(delays)} names seen twice) = {round((qv or 0) / 60, 1)} min, rounded "
                          f"up to the {step // 60}-min poll resolution: a name first shown during a gap is, with that "
                          "probability, seen again before W has passed, so first sightings later than W after a gap "
                          "are not re-sightings of a missed one"}


# ---- lead time vs OpenPhish ------------------------------------------------------------------------------------
RULES = {
    "E1_listed_at_first_poll": "present in the first OpenPhish poll: listed before the capture started",
    "E2_listing_interval_overlaps_gap": "the poll interval in which it was first listed overlaps a capture gap "
                                        "(listing time not known to the 30-min resolution)",
    "E3_unmatched_listed_after_gap_start": "no CT sighting and first listed after a gap began: its certificate may "
                                           "have been issued during the gap",
    "E4_ct_first_seen_within_W_of_start_or_gap_end": "CT first sighting within W after the capture start or a gap "
                                                     "end: an earlier sighting may have been missed",
}


def lead_time(listed: dict[str, float], ct_first, *, capture_start: float, gaps: list[tuple[float, float]],
              polls: list[float], w_s: float, min_matches: int = MIN_CT_FIRST, unit: str = "exact hostname") -> dict:
    """listed: key (host or eTLD+1) -> first_listed epoch. ct_first: key -> CT first_seen epoch or None.
    Every key lands in exactly one exclusion rule (first that applies) or is retained."""
    first_poll = min([*polls, *listed.values()]) if (polls or listed) else None
    poll_times = sorted(set(polls) | set(listed.values()))
    excl = Counter({k: 0 for k in RULES})
    leads, listed_first, unmatched_retained = [], 0, 0
    for key, t in listed.items():
        if first_poll is not None and t <= first_poll + 60:
            excl["E1_listed_at_first_poll"] += 1
            continue
        prev = max((p for p in poll_times if p < t - 60), default=None)
        if prev is not None and any(prev < ge and t > gs for gs, ge in gaps):
            excl["E2_listing_interval_overlaps_gap"] += 1
            continue
        ct = ct_first(key)
        if ct is None:
            if any(gs < t for gs, _ in gaps):
                excl["E3_unmatched_listed_after_gap_start"] += 1
            else:
                unmatched_retained += 1
            continue
        edges = [capture_start] + [ge for _, ge in gaps]
        if any(e <= ct < e + w_s for e in edges):
            excl["E4_ct_first_seen_within_W_of_start_or_gap_end"] += 1
            continue
        lead_h = (t - ct) / 3600
        if lead_h > 0:
            leads.append(lead_h)
        else:
            listed_first += 1
    n = len(leads)
    out = {"unit": unit, "entries": len(listed), "excluded": dict(excl), "excluded_total": sum(excl.values()),
           "retained_matched_ct_first": n, "retained_matched_listed_first": listed_first,
           "retained_unmatched": unmatched_retained}
    if n < min_matches:
        per_rule = ", ".join(k.split("_")[0] + " " + str(v) for k, v in excl.items())
        out.update(value=None, status=f"not measured: {n} CT-first matches on the {unit} (fewer than {min_matches}); "
                                      f"{len(listed)} OpenPhish entries, {sum(excl.values())} excluded "
                                      f"({per_rule}), "
                                      f"{listed_first} listed before CT showed them, {unmatched_retained} with no CT "
                                      "sighting")
    else:
        out.update(status="measured", lead_hours={"median": round(quantile(leads, .5), 2),
                                                  "p25": round(quantile(leads, .25), 2),
                                                  "p75": round(quantile(leads, .75), 2), "max": round(max(leads), 2),
                                                  "n": n})
    return out


def lead_time_section(sqlite_path: Path, *, capture: dict, gaps, polls, w: dict, etld1_fn=None,
                      allowlisted_fn=None) -> dict:
    """Exact-hostname and eTLD+1 lead time (reported separately, never mixed) with the A4(b) exclusions."""
    c = sqlite3.connect(f"file:{sqlite_path.as_posix()}?mode=ro", uri=True)
    try:
        hosts: dict[str, float] = {}
        urls = empty = 0
        for url, host, t in c.execute("select url, host, first_listed from openphish"):
            urls += 1
            h = (host or "").lower().rstrip(".")
            if not h:
                empty += 1
                continue
            hosts[h] = min(t, hosts.get(h, t))
        exact_cache: dict[str, float | None] = {}

        def exact(h):
            if h not in exact_cache:
                r = c.execute("select first_seen from ct_first_seen where name = ?", (h,)).fetchone()
                exact_cache[h] = r[0] if r else None
            return exact_cache[h]
        kw = dict(capture_start=capture["start"], gaps=gaps, polls=polls, w_s=w["seconds"])
        ex = lead_time(hosts, exact, unit="exact hostname", **kw)
        unmatched = [h for h in hosts if exact(h) is None]
        if allowlisted_fn:
            ex["unmatched_allowlisted_not_indexed"] = sum(1 for h in unmatched if allowlisted_fn(h))
        out = {"exact_hostname": ex}
        if etld1_fn:
            by_e: dict[str, float] = {}
            for h, t in hosts.items():
                e = etld1_fn(h)
                by_e[e] = min(t, by_e.get(e, t))
            first_e: dict[str, float] = {}
            for name, fs in c.execute("select name, first_seen from ct_first_seen"):
                j = 0
                while True:  # every suffix of the name that is one of the listed eTLD+1s
                    suf = name[j:]
                    if suf in by_e and (suf not in first_e or fs < first_e[suf]):
                        first_e[suf] = fs
                    j = name.find(".", j) + 1
                    if j == 0:
                        break
            out["etld1"] = lead_time(by_e, first_e.get, unit="eTLD+1", **kw)
        polls_with_new = len({round(t) for t in hosts.values()})
        out.update(openphish_urls=urls, openphish_hosts=len(hosts), openphish_urls_without_host=empty,
                   polls_in_log=len(polls), polls_that_added_new_urls=polls_with_new)
        return out
    finally:
        c.close()


# ---- live pipeline (Supabase, read-only) ------------------------------------------------------------------------
def live_pipeline_counts(start: float, end: float, gap: tuple[float, float] | None) -> dict:
    import sqlalchemy as sa

    from services.api.db import engine
    from services.config import SETTINGS
    p = {"s": iso(start), "e": iso(end)}
    with engine().connect() as c:
        c.execute(sa.text("set transaction read only"))
        org = c.execute(sa.text("select id from organisations where slug = :s"), {"s": SETTINGS.pipeline_org}).scalar()
        base = ("from domains d where d.source = 'certstream' and d.origin_org_id is null "
                "and d.candidate_at >= cast(:s as timestamptz) and d.candidate_at <= cast(:e as timestamptz)")
        n, first, last = c.execute(sa.text(f"select count(*), min(candidate_at), max(candidate_at) {base}"), p).one()
        times = [r[0].timestamp() for r in c.execute(sa.text(f"select d.candidate_at {base} order by 1"), p)]
        status = dict(c.execute(sa.text(
            f"select coalesce(v.status, 'no verdict row (candidate)'), count(*) {base.replace('from domains d', 'from domains d left join domain_verdicts v on v.domain_id = d.id and v.org_id = :org')} group by 1"),
            {**p, "org": org}).all())
        touched = c.execute(sa.text(f"select count(*) {base} and d.last_seen > d.first_seen + interval '1 second'"),
                            p).scalar()
        across = None
        if gap:
            across = c.execute(sa.text(f"select count(*) {base} and d.first_seen < cast(:gs as timestamptz) "
                                       "and d.last_seen > cast(:ge as timestamptz)"),
                               {**p, "gs": iso(gap[0]), "ge": iso(gap[1])}).scalar()
        certs = c.execute(sa.text("select count(*) from certificates where source = 'certstream' and ct_seen_at >= "
                                  "cast(:s as timestamptz) and ct_seen_at <= cast(:e as timestamptz)"), p).scalar()
    pg = max(((b - a, a, b) for a, b in zip(times, times[1:])), default=None)
    win = {"from": iso(start), "to": iso(end)}
    verdicts = {k: int(v) for k, v in status.items()}
    return {
        "threshold": SETTINGS.triage_threshold, "window": win,
        "candidates": {"value": int(n), "first_candidate_at": first.isoformat() if first else None,
                       "last_candidate_at": last.isoformat() if last else None,
                       "dataset": "Supabase domains: source=certstream, shared (origin_org_id null), candidate_at in window"},
        "org_verdicts": {"org": SETTINGS.pipeline_org, "org_id": org, "by_status": verdicts,
                         "confirmed": verdicts.get("confirmed", 0), "dismissed": verdicts.get("dismissed", 0),
                         "unreachable": verdicts.get("unreachable", 0), "n_candidates": int(n),
                         "dataset": "domain_verdicts of the pipeline org for those candidates; status as of measured_at"},
        "pipeline_largest_gap": ({"from": iso(pg[1]), "to": iso(pg[2]), "minutes": round(pg[0] / 60, 1)} if pg else None),
        "redelivery": {"certificates_rows_in_window": int(certs), "candidate_rows_touched_again": int(touched),
                       "touched_again_across_the_gap": across,
                       "note": "certificates.fingerprint is unique and a repeat is absorbed by ON CONFLICT without a "
                               "counter, so certificate re-deliveries are not measurable. domains.last_seen is touched "
                               "on every repeat candidate sighting (precertificate + final certificate, other logs, "
                               "re-delivery); rows first seen before the gap and touched after it bound restart "
                               "re-deliveries from above"},
        "measured_at": now_iso()}


# ---- orchestration ----------------------------------------------------------------------------------------------
def capture_state(fixture: Path, last_seen: float) -> tuple[str, dict | None]:
    """complete only when the final run wrote its .summary.json (record_ct writes it on a normal end)."""
    p = Path(str(fixture) + ".summary.json")
    if not p.exists():
        return "partial", None
    summ = json.loads(p.read_text(encoding="utf-8"))
    fin = datetime.fromisoformat(summ["finished"]).timestamp() if summ.get("finished") else 0
    return ("complete" if fin >= last_seen - 600 else "partial"), summ


def analyze(fixture: Path = FIXTURE_IN, sqlite_path: Path = SQLITE_IN, log: Path = LOG_IN, *,
            fixture_out: Path | None = None, skip_live: bool = False, threshold: float | None = None,
            triage_fn=None) -> dict:
    """Everything finalize measures, as metrics.json sections: ct_capture, live_pipeline_counts, lead_time."""
    from services.config import SETTINGS
    from services.ingest.brands import etld1
    if triage_fn is None:
        from services.ingest.triage import triage as triage_fn
    for p, what in ((fixture, "CT fixture"), (sqlite_path, "first-seen/OpenPhish SQLite"), (log, "recorder log")):
        if not Path(p).exists():
            raise InputError(f"missing input: {what} {p}")
    c = sqlite3.connect(f"file:{Path(sqlite_path).as_posix()}?mode=ro", uri=True)
    tables = {r[0] for r in c.execute("select name from sqlite_master where type = 'table'")}
    c.close()
    if not {"ct_first_seen", "openphish"} <= tables:
        raise InputError(f"{sqlite_path}: tables ct_first_seen and openphish required, found {sorted(tables)}")
    threshold = SETTINGS.triage_threshold if threshold is None else threshold
    s = scan_capture(Path(fixture), threshold=threshold, fixture_out=fixture_out, triage_fn=triage_fn)
    if not s.seen:
        raise InputError(f"{fixture}: no certificate messages with data.seen")
    start, end = min(s.seen), max(s.seen)
    state, summ = capture_state(Path(fixture), end)
    gaps = find_gaps(s.seen)
    logd = parse_log(Path(log).read_text(encoding="utf-8", errors="replace"),
                     datetime.fromtimestamp(start, timezone.utc).date())
    w = resighting_window(s.name_sightings)
    window = {"from": iso(start), "to": iso(end), "hours": round((end - start) / 3600, 2), "state": state}
    runs = [{"run": k, "messages": v["messages"], "first_seen": iso(v["first_seen"]), "last_seen": iso(v["last_seen"])}
            for k, v in sorted(s.members.items())]
    cov = coverage(s.minutes, s.op_minutes, start, end, gaps)
    for op, d in cov["per_operator"].items():
        d["messages"] = s.op_messages[op]
        d["logs"] = sorted(s.op_logs[op])
    total_gap = sum(b - a for a, b in gaps)
    seen_sorted = sorted(s.seen)
    dataset = f"data/replay/ct_live.jsonl.gz ({state} capture), certstream-server-go lite stream"
    ct_capture = {
        "state": state, "window": window, "dataset": dataset,
        "runs": runs, "gzip_reader": {k: v for k, v in s.reader.items() if k != "decode_errors"} | {
            "decode_errors": s.reader.get("decode_errors", [])},
        "messages": {"total": s.messages, "by_tag": dict(s.by_tag), "bad_json": s.bad_json, "without_seen": s.no_seen},
        "gap": {"threshold_s": GAP_S, "gaps": [{"from": iso(a), "to": iso(b), "minutes": round((b - a) / 60, 1)}
                                               for a, b in gaps],
                "total_minutes": round(total_gap / 60, 1),
                "largest_other_interarrival_s": round(max((b - a for a, b in zip(seen_sorted, seen_sorted[1:])
                                                           if b - a < GAP_S), default=0), 1),
                "recorder_log": {"largest_silence": logd["largest_silence"], "reconnects": logd["reconnects"],
                                 "openphish_polls": len(logd["polls"]), "openphish_poll_failures": logd["poll_failures"]},
                "method": "max inter-arrival gap of data.seen over all messages (>= 300 s counts as a gap), "
                          "cross-checked with the recorder log"},
        "coverage": cov | {"method": "minutes with >= 1 message (all messages: scored + 1 % sample) / minutes in the "
                                     "window; operator from data.source url/name",
                           "note": "The fixture keeps a 1 % background sample, so a low-volume operator can miss a "
                                   "minute without any capture loss: pct_outside_gaps separates that from the gap"},
        "duplicates": dict(s.dup) | {"n_messages": s.messages,
                                     "definition": "same_certificate: same leaf sha256 (else log url + cert_index) "
                                                   "seen again, including the same certificate from another CT log; "
                                                   "same_log_entry_redelivered: identical log url + cert_index; "
                                                   "*_across_runs: the first copy is in an earlier run (gzip member)"},
        "candidates_at_threshold": s.candidates | {
            "threshold": threshold, "rules": "services.ingest.triage.triage as deployed", "window": window,
            "dataset": dataset,
            "coverage_note": "The fixture holds every certificate that scored >= 0.20 when recorded plus a 1 % sample "
                             "of the rest; a certificate the deployed rules would now score >= threshold but scored < "
                             "0.20 at recording is only present if sampled"},
        "resighting_window_W": w,
        "measured_at": now_iso(),
    }
    if summ:
        ct_capture["recorder_summary"] = {k: summ.get(k) for k in ("started", "finished", "certs", "kept_scored",
                                                                    "kept_sample", "candidates_at_0_35", "sample",
                                                                    "keep_score")}
    if s.fixture is not None:
        s.fixture.update(window=window, gaps=ct_capture["gap"]["gaps"], messages_in=s.messages,
                         duplicates_removed=s.messages - s.fixture["messages"],
                         sample_rate=(summ or {}).get("sample", 0.01), keep_score=(summ or {}).get("keep_score", 0.20),
                         replay_note=f"stream.py replay sleeps min(delta / speed, {REPLAY_SLEEP_CAP_S} s) between "
                                     "messages; the capture gap therefore costs at most 2 s",
                         state=state, measured_at=now_iso())
        ct_capture["replay_fixture"] = s.fixture
    else:
        ct_capture["replay_seconds_at_speed_360_all_messages"] = round(replay_seconds(seen_sorted), 1)

    lt = lead_time_section(Path(sqlite_path), capture={"start": start}, gaps=gaps, polls=logd["polls"], w=w,
                           etld1_fn=etld1,
                           allowlisted_fn=lambda h: any(r.feature == "allowlisted" for r in triage_fn(h).reasons))
    lt.update(window=window, state=state, rules=RULES, W=w, min_ct_first_matches=MIN_CT_FIRST,
              listing_time_resolution="+/-30 min: the OpenPhish feed is polled every 30 min, so a URL's listing time "
                                      "lies in the 30 min before the poll that first saw it",
              match_rule="exact hostname of the OpenPhish URL == a name in ct_first_seen (non-allowlisted names "
                         "from every certificate in the capture); eTLD+1 matches reported separately, never mixed",
              dataset=f"OpenPhish public feed polled every 30 min x CT first sighting (ct_live.sqlite), {state} capture",
              measured_at=now_iso())
    lt["status"] = lt["exact_hostname"]["status"]
    if skip_live:
        live = {"unavailable": "--skip-live given: the live pipeline database was not queried", "window": window}
    else:
        try:
            live = live_pipeline_counts(start, end, max(gaps, key=lambda g: g[1] - g[0]) if gaps else None)
        except Exception as e:  # never silently skipped: finalize stops and says how to proceed
            first = str(e).strip().splitlines()[0][:200] if str(e).strip() else ""
            raise InputError(f"live pipeline database query failed ({type(e).__name__}: {first}); fix DATABASE_URL "
                             "or pass --skip-live to record the live counts as not measured") from e
        live["state"], live["window"] = state, window
    return {"ct_capture": ct_capture, "lead_time": lt, "live_pipeline_counts": live}


def merge_metrics(existing: dict, sections: dict) -> dict:
    """New sections in; the old 30-min PhishTank lead time is kept under its own key, never overwritten."""
    m = dict(existing)
    old = m.get("lead_time")
    if isinstance(old, dict) and "PhishTank" in str(old.get("dataset", "")) and "lead_time_phishtank_30min" not in m:
        m["lead_time_phishtank_30min"] = old
    m.update(sections)
    m["generated_at"] = now_iso()
    return m


def summary_lines(sec: dict) -> list[str]:
    cc, lt, lv = sec["ct_capture"], sec["lead_time"], sec["live_pipeline_counts"]
    w = cc["window"]
    out = [f"capture: {cc['state'].upper()}  window {w['from']} -> {w['to']} ({w['hours']} h), "
           f"{cc['messages']['total']:,} messages in {len(cc['runs'])} runs"]
    for g in cc["gap"]["gaps"]:
        out.append(f"gap: {g['from']} -> {g['to']} = {g['minutes']} min")
    cv = cc["coverage"]
    out.append(f"coverage overall: {cv['pct']}% of {cv['minutes_in_window']} min")
    for op, d in cv["per_operator"].items():
        out.append(f"  {op:14} {d['pct']:6}%  (outside gaps {d['pct_outside_gaps']}%, {d['messages']:,} msgs)")
    du = cc["duplicates"]
    out.append(f"duplicates: same certificate {du.get('same_certificate', 0):,} (across runs "
               f"{du.get('same_certificate_across_runs', 0):,}); same log entry re-delivered "
               f"{du.get('same_log_entry_redelivered', 0):,} (across runs "
               f"{du.get('same_log_entry_redelivered_across_runs', 0):,})")
    ca = cc["candidates_at_threshold"]
    out.append(f"candidates at {ca['threshold']}: {ca['certificates']:,} certificates, {ca['unique_names']:,} unique "
               f"names ({ca['messages']:,} messages)")
    if "unavailable" in lv:
        out.append(f"live pipeline: not measured: {lv['unavailable']}")
    else:
        ov = lv["org_verdicts"]
        out.append(f"live pipeline {lv['window']['from']} -> {lv['window']['to']}: {lv['candidates']['value']:,} "
                   f"candidates; {ov['org']} confirmed {ov['confirmed']}, dismissed {ov['dismissed']}, unreachable "
                   f"{ov['unreachable']} (by status {ov['by_status']})")
    out.append(f"lead time (exact host): {lt['exact_hostname']['status']}")
    if "lead_hours" in lt["exact_hostname"]:
        out.append(f"  lead hours {lt['exact_hostname']['lead_hours']}")
    if "etld1" in lt:
        out.append(f"lead time (eTLD+1, separate): {lt['etld1']['status']}")
    out.append(f"W = {cc['resighting_window_W']['seconds'] / 60:.0f} min ({cc['resighting_window_W']['derivation'][:60]}...)")
    fx = cc.get("replay_fixture")
    if fx:
        out.append(f"fixture: {fx['path']} {fx['messages']:,} messages (removed {fx['duplicates_removed']:,} duplicates), "
                   f"replay at 360x = {fx['replay_seconds_at_speed']['360'] / 60:.1f} min")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fixture", default=str(FIXTURE_IN))
    ap.add_argument("--sqlite", default=str(SQLITE_IN))
    ap.add_argument("--log", default=str(LOG_IN))
    ap.add_argument("--metrics", default=str(METRICS), help="base metrics.json the new sections are merged into")
    ap.add_argument("--out-dir", help="write metrics.json, REPORT.md and the fixture here instead")
    ap.add_argument("--allow-partial", action="store_true",
                    help="write a PARTIAL capture to the real outputs (default: partial -> preview locations)")
    ap.add_argument("--skip-live", action="store_true", help="do not query Supabase (recorded as not measured)")
    a = ap.parse_args(argv)
    try:
        if not Path(a.metrics).exists():
            raise InputError(f"missing input: base metrics {a.metrics} (run scripts.evaluate first)")
        if not a.skip_live:
            from services.config import SETTINGS
            if not SETTINGS.database_url:
                raise InputError("DATABASE_URL is not set (.env); pass --skip-live to record the live counts as "
                                 "not measured")
        summ_path = Path(a.fixture + ".summary.json")
        partial_guess = not summ_path.exists()
        if a.out_dir:
            rep_dir = data_dir = Path(a.out_dir)
        elif partial_guess and not a.allow_partial:
            rep_dir, data_dir = ROOT / "reports/finalize_preview", ROOT / "data/replay/finalize_preview"
        else:
            rep_dir, data_dir = None, ROOT / "data/replay"
        print(f"finalize: capture {'partial (no .summary.json yet)' if partial_guess else 'has a summary'}; "
              f"outputs -> {rep_dir or 'reports/metrics.json + docs/REPORT.md'}, fixture -> {data_dir}", flush=True)
        sec = analyze(Path(a.fixture), Path(a.sqlite), Path(a.log), fixture_out=data_dir / "ct_24h.jsonl.gz",
                      skip_live=a.skip_live)
    except InputError as e:
        print(f"finalize: ERROR: {e}", file=sys.stderr)
        return 2
    fx = sec["ct_capture"]["replay_fixture"]
    (data_dir / "ct_24h.summary.json").write_text(json.dumps(fx, indent=1), encoding="utf-8")
    from scripts import evaluate
    from scripts.build_report import render
    # the evaluate.py sections own the metrics.json shape; finalize hands them the one-pass analysis
    sections = {k: getattr(evaluate, k)(sec) for k in ("ct_capture", "live_pipeline_counts", "lead_time")}
    broken = [k for k, v in sections.items() if "trace" in v]
    if broken:
        why = "; ".join(k + ": " + str(sections[k]["unavailable"]) for k in broken)
        print(f"finalize: ERROR: sections failed: {why}", file=sys.stderr)
        return 3
    metrics = merge_metrics(json.loads(Path(a.metrics).read_text(encoding="utf-8")), sections)
    if rep_dir is None:
        m_out, r_out = METRICS, ROOT / "docs/REPORT.md"
    else:
        rep_dir.mkdir(parents=True, exist_ok=True)
        m_out, r_out = rep_dir / "metrics.json", rep_dir / "REPORT.md"
    m_out.write_text(json.dumps(metrics, indent=1, default=str), encoding="utf-8")
    r_out.write_text(render(metrics), encoding="utf-8")
    for line in summary_lines(sec):
        print(line)
    print(f"wrote {m_out}\nwrote {r_out}\nwrote {data_dir / 'ct_24h.jsonl.gz'} (+ .summary.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
