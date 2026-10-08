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


def _live(after=None):
    before = {"n_domains": 1435, "since": "2026-10-07T06:30:36Z", "measured_at": "2026-10-07T18:33:46Z",
              "verdicts": {"candidate": 445, "unreachable": 776, "dismissed": 214}, "pages_assessed": 659,
              "with_at_least_one_strong_signal": 0, "strong_signals_by_detector": {},
              "favicon_census": {"pages_with_favicon": 432, "own_brand_match": 0, "any_brand_match": 3,
                                 "reference_brands": 34, "reference_hashes": 73},
              "unreachable": {"n": 776, "by_cause": {"HTTP 404 error page": 391, "dns: name does not resolve": 142},
                              "top_sites": [["kennelstudio.com", 318]], "distinct_sites": 300,
                              "excluding_top_site": {"site": "kennelstudio.com", "n": 458}}}
    g = {"measured_at": "2026-10-07T18:17:48Z", "dataset": {"reachable_with_credential_input": 14, "labelled_pages": 45},
         "S1": {"false_positives": 0, "legit_pages_tested": 39, "ships_as": "strong", "false_positive_pages": []},
         "S2": {"false_positives": 0, "legit_pages_tested": 39, "ships_as": "strong", "false_positive_pages": []},
         "S2_hits_by_source": {"request fired during page load": 0, "page code": 0}}
    r1 = {**g, "dataset": {"reachable_with_credential_input": 18, "labelled_pages": 45},
          "S2": {"false_positives": 6, "legit_pages_tested": 43, "ships_as": "MODERATE", "false_positive_pages": ["a"] * 6},
          "S2_hits_by_source": {"request fired during page load": 14, "page code": 1}}
    ho = {**g, "dataset": {"legit_login_pages": 45, "reachable_with_credential_input": 13, "labelled_pages": 54},
          "S2": {"false_positives": 1, "legit_pages_tested": 40, "ships_as": "MODERATE", "false_positive_pages":
                 ["https://www.twitch.tv/login"]},
          "false_positive_detail": {"S1": [], "S2": [{"page": "https://www.twitch.tv/login",
                                                     "destination": "https://eppo.cloud",
                                                     "where": "https://assets.twitch.tv/assets/flags-1.js"}]}}
    return {"before": before, "after": after, "brands_total": 40,
            "gates": {"run1": r1, "run2": g, "run2_retest": None, "holdout": ho},
            "signal_strengths": {"exfil": "strong", "js_post": "moderate"}}


def test_live_confirmation_reports_the_measured_zero_its_cause_and_sample_sizes():
    md = render(metrics(live_confirmation=_live()))
    assert "**0** came back with any strong signal" in md                 # C2: the defined term, verbatim
    assert "of the 432 live domains with a favicon, 0 appeared with their own brand's icon" in md
    assert "meesho-all.cfd" in md
    assert "evidence, not proof" in md and "18" in md and "45" in md     # S3c: sample size next to the 0-FP claim
    assert "kennelstudio.com" in md and "318" in md
    assert "S4 re-check: not yet measured" in md


def test_same_origin_relay_limitation_ties_back_to_infrastructure():
    md = render(metrics())
    assert "/dev-api/mobileUser" in md and "after the data leaves the browser" in md
    assert "shared infrastructure" in md
    assert "clustering takes confirmed domains as its input" in md   # stated as built, not as a capability


def test_counts_are_defined_once_at_the_top_of_results():
    """C2: one definitions block, before any result, so 1,435 / 659 / 776 / 432 / 0 / 0 cannot be conflated."""
    md = render(metrics(live_confirmation=_live()))
    results = md.index("## Results")
    block = md[results:md.index("### Detection: triage", results)]
    for term, count in (("live domains in the capture window", "1,435"), ("assessed", "659"),
                        ("unreachable", "776 (318 from kennelstudio.com)"), ("with a favicon", "432"),
                        ("with their own brand's icon", "0"), ("with any strong signal", "0")):
        assert f"| {term} | {count} |" in block, term


def test_held_out_methodology_is_stated_not_just_the_result():
    """C1: refined on development pages, evaluated once on held-out pages, NOT re-tuned on them, hence moderate."""
    md = render(metrics(live_confirmation=_live()))
    assert "18 development pages" in md and "45 held-out legitimate login pages" in md
    assert "eppo.cloud" in md and "twitch.tv" in md
    assert "not** re-tuned against the held-out set" in md and "training set" in md


def test_what_the_zero_means_is_said_plainly_with_provenance():
    """C4: detects at live scale; clusters and plans on SEEDED data; does not confirm by page content on live traffic."""
    after = {**_live()["before"], "measured_at": "2026-10-08T00:30:00Z", "verdicts": {"candidate": 600, "unreachable": 835},
             "strong_signals_by_detector": {"credential_exfil_endpoint": 0}}
    md = render(metrics(live_confirmation=_live(after=after)))
    assert "it does not currently confirm by page content on live traffic" in md
    assert "seeded" in md and "no live domain has reached the campaign layer" in md


def test_where_the_live_pipeline_stops_is_stated_in_results():
    """D1: everything after confirmation takes confirmed domains as input; with none confirmed the live pipeline ends
    at the confirmation gate. Said directly in Results, not left to be inferred from campaign counts."""
    md = render(metrics(live_confirmation=_live()))
    results = md[md.index("## Results"):md.index("### Detection: triage")]
    assert "the live pipeline currently ends at the confirmation gate" in results
    assert "seeded campaign" in results


def test_infrastructure_entry_path_is_named_as_future_work_not_a_capability():
    """D2: infrastructure co-location as an entry path into a campaign, named precisely and marked not built."""
    md = render(metrics())
    fw = md[md.index("## Future work"):]
    assert "Infrastructure co-location as an entry path into a campaign" in fw
    assert "stays a candidate" in fw and "Not built" in fw


def test_live_campaign_membership_is_a_measured_number():
    """E3: 'nothing live reached the campaign layer' is shown as a measured count in a table, not as prose."""
    after = {**_live()["before"], "measured_at": "2026-10-08T00:30:00Z", "verdicts": {"candidate": 600, "unreachable": 835},
             "strong_signals_by_detector": {}, "in_a_campaign": 0}
    md = render(metrics(live_confirmation=_live(after=after)))
    results = md[md.index("## Results"):md.index("### Detection: triage")]
    assert "| live domains in a campaign | 0 |" in results
    assert "| live domains confirmed | 0 |" in results


def test_s4_reports_which_signals_fired_at_any_strength():
    after = {**_live()["before"], "measured_at": "2026-10-08T01:57:58Z", "verdicts": {"candidate": 435},
             "strong_signals_by_detector": {}, "in_a_campaign": 0,
             "s1_s2_census": {"S1_domains": {}, "S2_domains": {"moderate": 6},
                              "S2_destination_sites": {"contaboserver.net": 3, "shopifysvc.com": 2, "mydukaan.io": 1}}}
    md = render(metrics(live_confirmation=_live(after=after)))
    assert "S1 fired on 0 live domains" in md
    assert "S2 fired on 6 live domains (moderate)" in md and "shopifysvc.com 2" in md


def test_modern_kit_note_states_the_shipped_outcome_from_the_data():
    m = metrics()
    m["confirmation"] = {**m["confirmation"], "by_family": {"modern_js_kit": {"truth": "phishing", "n": 7, "confirmed": 0}}}
    md = render(m)
    assert "With the shipped strengths, 0 of the 7 modern JS-kit cases are confirmed" in md


def test_empty_detector_breakdown_reads_none():
    after = {**_live()["before"], "measured_at": "2026-10-08T02:09:52Z", "verdicts": {"candidate": 435},
             "strong_signals_by_detector": {}, "in_a_campaign": 0}
    md = render(metrics(live_confirmation=_live(after=after)))
    assert "(by detector: none)" in md and "`{}`" not in md
