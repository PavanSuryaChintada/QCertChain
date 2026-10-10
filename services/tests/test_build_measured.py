"""The home page's step times are generated from reports/metrics.json (and reports/api_latency.json), never typed:
owner rule, and owner decision 2026-10-10 (measured step times, no speed claim against blocklists)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

METRICS = {
    "triage_rules": {"latency_us_per_name": {"p50": 294.5, "p95": 1519.2, "n": 200000,
                                             "measured_at": "2026-10-06T14:30:31+00:00"}},
    "response_time": {
        "ct_seen_to_candidate_s": {"p50": 23.654, "p95": 32.1, "n": 114},
        "upstream_aggregator_delay_s": {"p50": 20.994, "p95": 30.233, "n": 114},
        "our_receipt_to_candidate_s": {"p50": 2.053, "p95": 5.443, "n": 114},
        "candidate_to_verdict_s": {"p50": 1.552, "p95": 22.653, "n": 106},
        "verdicts_from_live_candidates": {"unreachable": 102, "candidate": 10, "dismissed": 2},
        "evidence_created_to_anchored_s": {"p50": "2044.784", "p95": "2098.746", "n": 400},
        "interdiction_cpsat_solve_ms_api": {"p50": 131, "max": 4544, "n": 5},
        "measured_at": "2026-10-06T19:16:44+00:00",
    },
}
LATENCY = {"org1 GET evidence/verify": {"p95_ms": 138.7, "budget_ms": 400}}


def steps(metrics=METRICS, latency=LATENCY):
    from scripts.build_measured import steps as build
    return {s["id"]: s for s in build(metrics, latency)}


def test_each_step_carries_the_measured_values_formatted():
    s = steps()
    assert [k for k in s] == ["relay", "triage", "candidate", "verdict", "plan", "verify"]  # pipeline order
    assert (s["relay"]["value"], s["relay"]["p95"], s["relay"]["n"]) == ("21 s", "30 s", "114")
    assert (s["triage"]["value"], s["triage"]["p95"], s["triage"]["n"]) == ("0.29 ms", "1.5 ms", "200,000")
    assert (s["candidate"]["value"], s["candidate"]["p95"]) == ("2.1 s", "5.4 s")
    assert (s["verdict"]["value"], s["verdict"]["p95"]) == ("1.6 s", "23 s")
    assert s["verdict"]["unreachable"] == "102 of 114"
    assert (s["plan"]["value"], s["plan"]["slowest"], s["plan"]["n"]) == ("131 ms", "4.5 s", "5")
    assert (s["verify"]["value"], s["verify"]["stat"]) == ("139 ms", "p95")
    assert s["triage"]["at"] == "6 October 2026"


def test_a_step_that_was_not_measured_is_left_out_never_invented():
    m = json.loads(json.dumps(METRICS))
    del m["response_time"]["candidate_to_verdict_s"]
    m["triage_rules"]["latency_us_per_name"] = {"unavailable": "not run"}
    s = steps(m, {})
    assert "verdict" not in s and "triage" not in s and "verify" not in s
    assert "relay" in s


def test_anchoring_time_is_not_shown_while_it_includes_queueing():
    assert "anchor" not in steps()


def test_the_console_file_matches_the_measurements_in_the_repo():
    """Hand-editing apps/console/src/explain/measured.ts fails here: regenerate with python -m scripts.build_measured."""
    from scripts.build_measured import render
    metrics = json.loads((ROOT / "reports/metrics.json").read_text(encoding="utf-8"))
    latency = json.loads((ROOT / "reports/api_latency.json").read_text(encoding="utf-8"))
    assert (ROOT / "apps/console/src/explain/measured.ts").read_text(encoding="utf-8") == render(metrics, latency)
