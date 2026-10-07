import json

from scripts.build_report import render


def metrics(**over):
    m = json.load(open("reports/metrics.json", encoding="utf-8"))
    m.update(over)
    return m


def test_unavailable_section_says_not_measured_never_a_number():
    md = render(metrics(lead_time={"unavailable": "ConnectionError: crt.sh unreachable"}))
    assert "not measured: ConnectionError: crt.sh unreachable" in md


def test_numbers_come_from_metrics():
    m = metrics()
    md = render(m)
    assert str(m["triage_rules"]["latency_us_per_name"]["p50"]) in md
    assert str(m["confirmation"]["precision"]["value"]) in md


def test_quantum_framing_verbatim_and_never_a_heading():
    md = render(metrics())
    assert ("Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; the same "
            "formulation runs on QAOA. Quantum is not in the critical path.") in md
    assert not any(line.startswith("#") and "quantum" in line.lower() for line in md.splitlines())


def test_no_stale_name_and_states_reports_never_sent():
    md = render(metrics())
    assert "SEVER" not in md and "never sent" in md.lower()


def test_evidence_and_ledger_results_are_reported():
    md = render(metrics())
    assert "Evidence and ledger" in md and "tamper" in md.lower()


def test_precision_with_zero_recall_is_not_reported_as_a_number():
    m = metrics()
    m["triage_rules"]["recall_all_global_phishing"]["value"] = 0.0
    md = render(m)
    assert "Precision at the real 1:1000 base rate is 0.0" not in md


def test_proper_nouns_keep_their_case():
    md = render(metrics())
    assert "bradesco" not in md and "phishtank was" not in md


def test_missed_targets_are_said_plainly():
    md = render(metrics())
    assert "misses the 20 s target" in md and "5 ms" in md


def test_qubo_claim_is_scoped_and_qaoa_warm_start_disclosed():
    """Review I9: the x-only QUBO is exact only up to second order, and QAOA starts from the greedy plan."""
    md = render(metrics())
    assert "exact x-only" not in md
    assert "exact up to second order" in md
    assert "warm start" in md and "greedy" in md


def test_trust_boundaries_section_states_chain_public_and_api_org_scoped():
    md = render(metrics())
    sec = md[md.index("## Trust boundaries"):]
    sec = sec[:sec.index("\n## ", 5)]
    for must in ("deliberately public", "no domain names", "strictly org-scoped", "404", "different trust boundaries"):
        assert must in sec, must


def test_ai_assistance_is_declared_plainly():
    md = render(metrics())
    sec = md[md.index("## AI assistance"):]
    assert "AI coding agent" in sec and "human-directed" in sec and "docs/AI_USAGE_LOG.md" in sec


def test_consortium_steps_are_numbered_in_the_report():
    md = render(metrics())
    sec = md[md.index("## Trust boundaries"):]
    sec = sec[:sec.index("\n## ", 5)]
    for step in ("1. ", "2. ", "3. "):
        assert step in sec
    assert "404" in sec and "kit hash" in sec and "no names" in sec.lower()


def test_mutation_check_is_reported():
    md = render(metrics())
    assert "all 5 tenancy tests" in md and "row-level security" in md and "independently" in md


def test_threshold_decision_reasoning_and_full_sweep_are_reported():
    md = render(metrics())
    assert "a candidate is not a verdict" in md.lower()
    assert "fetch budget" in md and "two strong signals" in md
    rows = [l for l in md.splitlines() if l.startswith("| 0.") and l.count("|") >= 8]
    assert [l.split("|")[1].strip() for l in rows] == [f"{0.20 + 0.05 * i:.2f}" for i in range(13)]
    assert "never an even" in md or "not on an even" in md


def test_limits_name_http_only_and_compromised_sites_separately():
    md = render(metrics())
    lim = md[md.index("## Limits"):]
    assert "HTTP-only phishing" in lim and "compromised legitimate site" in lim and "out of CT scope" in lim


# ---- the 24-hour capture sections (npm run finalize) ------------------------------------------------------------
def _finalized(tmp_path, n_ct_first=12):
    from scripts import finalize as fz
    from services.tests.test_finalize import stub_triage, synthetic_capture
    fx, db, log = synthetic_capture(tmp_path, n_ct_first)
    a = fz.analyze(fx, db, log, fixture_out=tmp_path / "fx.jsonl.gz", skip_live=True, threshold=0.35,
                   triage_fn=stub_triage)
    a["live_pipeline_counts"] = {
        "threshold": 0.35, "state": "partial", "window": a["ct_capture"]["window"],
        "candidates": {"value": 1311, "first_candidate_at": "2026-10-07T06:37:03Z", "last_candidate_at": "x",
                       "dataset": "Supabase domains"},
        "org_verdicts": {"org": "org1", "by_status": {"dismissed": 80}, "confirmed": 0, "dismissed": 80,
                         "unreachable": 255, "n_candidates": 1311, "dataset": "domain_verdicts"},
        "pipeline_largest_gap": {"from": "a", "to": "b", "minutes": 39.8},
        "redelivery": {"candidate_rows_touched_again": 137, "touched_again_across_the_gap": 13, "note": "n"},
        "measured_at": "t"}
    return fz.merge_metrics(metrics(), a)


def _sec(md, head):
    s = md[md.index(head):]
    return s[:s.index("\n#", 5)]


def test_capture_section_reports_coverage_gap_duplicates_and_partial(tmp_path):
    m = _finalized(tmp_path)
    md = render(m)
    sec = _sec(md, "### CT capture")
    assert "PARTIAL capture" in sec and "Capture gap:" in sec and "min**" in sec
    assert "| **All operators** |" in sec and "| Google |" in sec and "| Let's Encrypt |" in sec
    assert "Duplicates: 1 messages" in sec and "across a restart" in sec
    assert "1 candidate certificates" in sec and "12 unique candidate names" in sec
    assert "Replay at 360× takes" in sec


def test_live_counts_section(tmp_path):
    md = render(_finalized(tmp_path))
    sec = _sec(md, "### Live pipeline counts at threshold 0.35")
    assert "| Live candidates from CT | 1,311 |" in sec and "| org1 dismissed | 80 | 1,311 candidates |" in sec
    assert "39.8 min" in sec


def test_lead_time_section_measured_with_exclusions_and_resolution(tmp_path):
    md = render(_finalized(tmp_path))
    sec = _sec(md, "### Lead time over phishing feeds")
    assert "Lead time, exact hostname: median" in sec and "n = 12" in sec
    assert "+/-30 min" in sec and "| E1: " in sec and "| E4: " in sec and "eTLD+1 (reported separately" in sec
    assert "lead_time_phishtank_30min" in sec


def test_lead_time_section_not_measured_below_10(tmp_path):
    md = render(_finalized(tmp_path, n_ct_first=4))
    sec = _sec(md, "### Lead time over phishing feeds")
    assert "not measured: 4 CT-first matches" in sec and "median" not in sec.split("eTLD+1")[0]
    assert "lead time over OpenPhish is not measured: 4 CT-first" in md  # the summary says so too


def test_new_sections_missing_render_not_measured():
    m = metrics()
    for k in ("ct_capture", "live_pipeline_counts"):
        m.pop(k, None)
    m["lead_time"] = {"unavailable": "no capture"}
    md = render(m)
    assert md.count("not measured: section missing (run npm run finalize)") == 2
    assert "not measured: no capture" in _sec(md, "### Lead time over phishing feeds")
