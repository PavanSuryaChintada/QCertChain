"""scripts/finalize.py on SMALL SYNTHETIC captures (tmp gzip + sqlite): restart dedup, gap exclusions, coverage,
lead time "not measured" below 10 matches, fixture sort/dedup, and a clear failure on a missing input."""
import gzip
import json
import sqlite3
import zlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scripts import finalize as fz

T0 = datetime(2026, 10, 7, 6, 0, tzinfo=timezone.utc).timestamp()
GOOGLE = {"name": "Google 'Argon2027h1'", "url": "https://ct.googleapis.com/logs/us1/argon2027h1"}
LE = {"name": "Let's Encrypt 'Willow2027h1'", "url": "https://mon.willow.ct.letsencrypt.org/2027h1"}


def msg(seen, fp, *, src=GOOGLE, ix=1, names=("a.example.com",), tag="background_sample"):
    return {"message_type": "certificate_update", "qcertchain_fixture": tag,
            "data": {"seen": seen, "cert_index": ix, "source": src,
                     "leaf_cert": {"sha256": fp, "all_domains": list(names), "issuer": {"O": "X"}}}}


def write_members(path, members, truncate=(0,)):
    """One gzip member per 'run'. Members in `truncate` get no end marker, as when a machine restart kills a run."""
    with open(path, "wb") as f:
        for k, msgs in enumerate(members):
            c = zlib.compressobj(6, zlib.DEFLATED, 31)
            body = "".join(json.dumps(m) + "\n" for m in msgs).encode()
            f.write(c.compress(body) + (c.flush(zlib.Z_SYNC_FLUSH) if k in truncate else c.flush()))


def stub_triage(name, issuer=None, san_count=1):
    score = 0.9 if "sbi" in name else 0.0
    feats = [SimpleNamespace(feature="allowlisted")] if name.endswith("allowed.com") else []
    return SimpleNamespace(score=score, reasons=feats)


# ---- reader + dedup ---------------------------------------------------------------------------------------------
def test_reads_every_member_even_when_a_run_was_cut_off(tmp_path):
    p = tmp_path / "c.jsonl.gz"
    write_members(p, [[msg(T0 + i, f"a{i}") for i in range(5)], [msg(T0 + 100 + i, f"b{i}") for i in range(3)]])
    with pytest.raises(Exception):  # the plain gzip reader fails at the second member: why finalize has its own
        list(gzip.open(p, "rt"))
    st = {}
    lines = list(fz.iter_lines(p, st))
    assert len(lines) == 8 and [k for k, _ in lines] == [0] * 5 + [1] * 3
    assert st["members"] == 2 and st["members_without_end_marker"] == 1


def test_partial_last_line_is_dropped_and_counted(tmp_path):
    p = tmp_path / "c.jsonl.gz"
    with open(p, "wb") as f:
        c = zlib.compressobj(6, zlib.DEFLATED, 31)
        f.write(c.compress((json.dumps(msg(T0, "x")) + "\n{\"data\": {\"se").encode()) + c.flush(zlib.Z_SYNC_FLUSH))
    st = {}
    assert len(list(fz.iter_lines(p, st))) == 1 and st["partial_lines_dropped"] == 1


def test_duplicates_counted_across_the_restart(tmp_path):
    p = tmp_path / "c.jsonl.gz"
    run1 = [msg(T0, "A", ix=1), msg(T0 + 1, "B", ix=2), msg(T0 + 2, "A", src=LE, ix=9)]   # A again from another log
    run2 = [msg(T0 + 3000, "B", ix=2),            # same log entry re-delivered after the restart
            msg(T0 + 3001, "A", src=LE, ix=10),   # A a third time, another log entry
            msg(T0 + 3002, "C", ix=3)]
    write_members(p, [run1, run2])
    s = fz.scan_capture(p, threshold=0.35, triage_fn=stub_triage)
    assert s.dup["same_certificate"] == 3 and s.dup["same_certificate_across_runs"] == 2
    assert s.dup["same_log_entry_redelivered"] == 1 and s.dup["same_log_entry_redelivered_across_runs"] == 1


def test_dedup_key_falls_back_to_log_and_index_without_fingerprint():
    d = {"cert_index": 7, "source": GOOGLE, "leaf_cert": {"all_domains": ["x.com"]}}
    assert fz.dedup_key(d) == f"ix:{GOOGLE['url']}#7"


# ---- gap + coverage ---------------------------------------------------------------------------------------------
def test_gap_found_and_coverage_counts_it():
    seen = [T0 + 30 * i for i in range(120)]                  # 60 min, a message every 30 s
    seen += [T0 + 3600 + 1200 + 30 * i for i in range(60)]   # 20-min gap, then 30 min
    gaps = fz.find_gaps(seen)
    assert gaps == [(T0 + 3570, T0 + 4800)]
    minutes = {int(s // 60) for s in seen}
    op = {"Google": minutes, "Sectigo": {m for m in minutes if m < int((T0 + 3600) // 60)}}
    cov = fz.coverage(minutes, op, min(seen), max(seen), gaps)
    assert cov["minutes_in_window"] == 110 and cov["minutes_covered"] == 90
    assert cov["minutes_inside_gaps"] == 20 and cov["pct"] == round(100 * 90 / 110, 2)
    assert cov["per_operator"]["Google"]["pct_outside_gaps"] == 100.0
    assert cov["per_operator"]["Sectigo"]["pct"] == round(100 * 60 / 110, 2)


def test_operator_mapping_from_real_source_fields():
    assert fz.operator_of(GOOGLE) == "Google" and fz.operator_of(LE) == "Let's Encrypt"
    assert fz.operator_of({"name": "PlumbersArms", "url": "https://storage.googleapis.com/x.goog"}) == "Google"
    assert fz.operator_of({"name": "TrustAsia Luoshu2027", "url": "https://luoshu2027.trustasia.com/l"}) == "TrustAsia"
    assert fz.operator_of({"name": "Cloudflare 'Nimbus2027'", "url": "https://ct.cloudflare.com/logs/n"}) == "Cloudflare"
    assert fz.operator_of({"name": "Microsec Eszigno2027h1", "url": "https://eszigno.hu"}) == "Other"


def test_log_parse_polls_and_day_rollover():
    log = "[23:40] openphish: 300 urls in feed\nreconnecting after X\n[00:10] openphish: 300 urls in feed\n"
    d = fz.parse_log(log, datetime(2026, 10, 7).date())
    assert d["polls"][1] - d["polls"][0] == 1800 and d["reconnects"] == 1


# ---- lead-time exclusion rules ----------------------------------------------------------------------------------
GAP = (T0 + 6 * 3600, T0 + 7 * 3600)
POLLS = [T0 + 60 + 1800 * i for i in range(12) if not GAP[0] <= T0 + 60 + 1800 * i < GAP[1]] + [GAP[1] + 30]
KW = dict(capture_start=T0, gaps=[GAP], polls=POLLS, w_s=5400)


def lt(listed, ct):
    return fz.lead_time(listed, ct.get, **KW)


def test_E1_listed_at_first_poll_is_excluded():
    r = lt({"a.com": T0 + 60}, {"a.com": T0 + 10})
    assert r["excluded"]["E1_listed_at_first_poll"] == 1 and r["retained_matched_ct_first"] == 0


def test_E2_listing_interval_overlapping_the_gap_is_excluded():
    r = lt({"a.com": GAP[1] + 30}, {"a.com": T0 + 2 * 3600})  # first poll after the gap: listed some time in the gap
    assert r["excluded"]["E2_listing_interval_overlaps_gap"] == 1


def test_E3_unmatched_after_gap_start_excluded_but_before_retained():
    r = lt({"late.com": GAP[1] + 1800 + 60, "early.com": T0 + 60 + 1800 * 3}, {})
    assert r["excluded"]["E3_unmatched_listed_after_gap_start"] == 1 and r["retained_unmatched"] == 1


def test_E4_first_seen_just_after_capture_start_or_gap_end_excluded():
    listed = {"s.com": T0 + 60 + 1800 * 5, "g.com": GAP[1] + 30 + 1800 * 4, "ok.com": T0 + 60 + 1800 * 5}
    ct = {"s.com": T0 + 600, "g.com": GAP[1] + 1200, "ok.com": T0 + 2 * 3600}
    r = lt(listed, ct)
    assert r["excluded"]["E4_ct_first_seen_within_W_of_start_or_gap_end"] == 2 and r["retained_matched_ct_first"] == 1


def test_lead_time_not_measured_below_10_with_counts():
    listed = {f"h{i}.com": T0 + 60 + 1800 * 5 for i in range(9)}
    r = lt(listed, {h: T0 + 2 * 3600 for h in listed})
    assert r["status"].startswith("not measured: 9 CT-first matches") and r["value"] is None
    assert "lead_hours" not in r and "9 OpenPhish entries" in r["status"]


def test_lead_time_measured_at_10_or_more():
    listed = {f"h{i}.com": T0 + 60 + 1800 * (5 + i % 2) for i in range(12)}
    r = lt(listed, {h: T0 + 2 * 3600 for h in listed})
    h = r["lead_hours"]
    assert r["status"] == "measured" and h["n"] == 12 and h["max"] == round((60 + 1800 * 6 - 7200) / 3600, 2)
    assert h["p25"] <= h["median"] <= h["p75"] <= h["max"]


def test_resighting_window_rounds_up_to_poll_resolution():
    w = fz.resighting_window({f"n{i}": [0, 60.0 * i] for i in range(1, 101)} | {"once": [0, None]})
    assert w["n_names_seen_twice"] == 100 and w["seconds"] == 7200  # p99 = 99 min -> 120 min
    assert fz.resighting_window({})["seconds"] == 1800


# ---- end to end on a synthetic capture: fixture, exact vs eTLD+1, replay time ------------------------------------
def synthetic_capture(tmp_path, n_ct_first=12):
    """06:00-16:00 UTC, gap 12:00-13:00, two runs. n_ct_first phishing hosts first seen at 08:00 and listed at
    11:00:30 (after the first poll), plus 3 hosts already in the first poll."""
    fx, db, log = tmp_path / "ct.jsonl.gz", tmp_path / "ct.sqlite", tmp_path / "rec.log"
    run1 = [msg(T0 + 60 * i, f"f{i}", ix=i, src=GOOGLE if i % 2 else LE) for i in range(360)]
    run2 = [msg(T0 + 7 * 3600 + 60 * i, f"g{i}", ix=1000 + i) for i in range(180)]
    run1.append(msg(T0 + 7200, "ph", ix=5000, names=[f"sbi-{k}.xyz" for k in range(n_ct_first)], tag="scored"))
    run2.append(msg(T0 + 7 * 3600 + 5, "f3", src=LE, ix=99))   # a cross-run duplicate certificate
    write_members(fx, [sorted(run1, key=lambda m: m["data"]["seen"]), run2])
    c = sqlite3.connect(db)
    c.execute("create table ct_first_seen (name text primary key, first_seen real not null, score real)")
    c.execute("create table openphish (url text primary key, host text not null, first_listed real not null)")
    c.executemany("insert into ct_first_seen values (?, ?, 0.9)", [(f"sbi-{k}.xyz", T0 + 7200) for k in range(n_ct_first)])
    c.executemany("insert into openphish values (?, ?, ?)",
                  [(f"https://sbi-{k}.xyz/login", f"sbi-{k}.xyz", T0 + 5 * 3600 + 30) for k in range(n_ct_first)]
                  + [(f"https://old{k}.com/", f"old{k}.com", T0 + 30) for k in range(3)])
    c.commit()
    c.close()
    polls = [f"[{h:02d}:{m:02d}] openphish: 300 urls in feed" for h in range(6, 16) for m in (0, 30) if not 12 <= h < 13]
    log.write_text("\n".join(polls) + "\n", encoding="utf-8")
    return fx, db, log


def test_analyze_end_to_end_builds_sorted_deduped_fixture(tmp_path):
    fx, db, log = synthetic_capture(tmp_path)
    out = tmp_path / "out" / "ct_24h.jsonl.gz"
    a = fz.analyze(fx, db, log, fixture_out=out, skip_live=True, threshold=0.35, triage_fn=stub_triage)
    cc = a["ct_capture"]
    assert cc["state"] == "partial" and len(cc["runs"]) == 2
    assert [g["minutes"] for g in cc["gap"]["gaps"]] == [round((7 * 3600 - 359 * 60) / 60, 1)]
    assert cc["duplicates"]["same_certificate_across_runs"] == 1
    assert cc["candidates_at_threshold"]["certificates"] == 1 and cc["candidates_at_threshold"]["unique_names"] == 12
    lines = [json.loads(x) for x in gzip.open(out, "rt", encoding="utf-8")]
    seen = [m["data"]["seen"] for m in lines]
    fps = [m["data"]["leaf_cert"]["sha256"] for m in lines]
    assert seen == sorted(seen) and len(fps) == len(set(fps)) == 541
    f3 = next(m for m in lines if m["data"]["leaf_cert"]["sha256"] == "f3")
    assert f3["data"]["seen"] == T0 + 180  # the earliest copy is kept
    rf = cc["replay_fixture"]
    assert rf["duplicates_removed"] == 1 and rf["replay_seconds_at_speed"]["360"] == round(fz.replay_seconds(seen), 1)
    assert fz.replay_sleep(3600) == 2.0  # the gap costs at most the 2 s cap
    lead = a["lead_time"]
    assert lead["exact_hostname"]["status"] == "measured" and lead["exact_hostname"]["lead_hours"]["n"] == 12
    assert lead["exact_hostname"]["excluded"]["E1_listed_at_first_poll"] == 3
    assert "etld1" in lead and lead["etld1"]["unit"] == "eTLD+1"
    assert a["live_pipeline_counts"]["unavailable"].startswith("--skip-live")


def test_analyze_lead_time_not_measured_with_few_matches(tmp_path):
    fx, db, log = synthetic_capture(tmp_path, n_ct_first=4)
    a = fz.analyze(fx, db, log, skip_live=True, threshold=0.35, triage_fn=stub_triage)
    assert a["lead_time"]["status"].startswith("not measured: 4 CT-first matches")


def test_missing_input_exits_nonzero_with_message(tmp_path, capsys):
    rc = fz.main(["--fixture", str(tmp_path / "nope.jsonl.gz"), "--skip-live", "--out-dir", str(tmp_path / "o")])
    assert rc == 2 and "missing input: CT fixture" in capsys.readouterr().err
    rc = fz.main(["--metrics", str(tmp_path / "none.json"), "--skip-live", "--out-dir", str(tmp_path / "o")])
    assert rc == 2 and "base metrics" in capsys.readouterr().err


def test_old_phishtank_lead_time_kept_under_its_own_key():
    old = {"lead_time": {"dataset": "our 30-min CT capture x PhishTank", "matched_domains": 11}}
    m = fz.merge_metrics(old, {"lead_time": {"status": "not measured: x"}})
    assert m["lead_time_phishtank_30min"]["matched_domains"] == 11 and m["lead_time"]["status"] == "not measured: x"


# ---- B6: a partial capture can never reach the real report ---------------------------------------------------
@pytest.mark.parametrize("allow_partial", [False, True])
def test_partial_capture_never_writes_the_real_report(allow_partial):
    m, r, d = fz.output_paths(partial=True, allow_partial=allow_partial, out_dir=None)
    assert m != fz.METRICS and r != fz.ROOT / "docs/REPORT.md"
    assert "finalize_preview" in str(m) and "finalize_preview" in str(r) and "finalize_preview" in str(d)


def test_complete_capture_writes_the_real_report():
    m, r, d = fz.output_paths(partial=False, allow_partial=False, out_dir=None)
    assert (m, r, d) == (fz.METRICS, fz.ROOT / "docs/REPORT.md", fz.ROOT / "data/replay")


def test_out_dir_wins(tmp_path):
    assert fz.output_paths(partial=True, allow_partial=True, out_dir=str(tmp_path)) == (
        tmp_path / "metrics.json", tmp_path / "REPORT.md", tmp_path)
