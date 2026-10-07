import json

from scripts.build_report import render


def metrics(**over):
    m = json.load(open("reports/metrics.json", encoding="utf-8"))
    m.update(over)
    return m


def test_unavailable_section_says_not_measured_never_a_number():
    md = render(metrics(lead_time={"unavailable": "ConnectionError: crt.sh unreachable"}))
    assert "not measured — ConnectionError: crt.sh unreachable" in md


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
