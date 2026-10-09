"""Backend of the demo pages (items 10-13): solver comparison + formulation, evidence verify with a SIMULATED tamper,
ledger events, the measured-metrics report, and the batched /status poll."""
import pytest

pytestmark = pytest.mark.db


def _bundle(api, campaign_id):
    g = api.get(f"/campaigns/{campaign_id}/graph").json()
    return api.get(f"/domains/{g['domains'][0][0]}").json()["evidence_bundle_id"]


def test_campaign_list_says_whether_there_is_a_plan_and_an_anchor(api, seeded):
    c = api.get("/campaigns").json()["items"][0]
    assert c["has_plan"] is False and c["anchored"] is False and c["last_seen"]
    api.post(f"/campaigns/{seeded}/interdict", json={"k": 2})
    assert api.get("/campaigns").json()["items"][0]["has_plan"] is True


def test_verify_three_checks_and_a_simulated_tamper_that_never_touches_the_evidence(api, seeded):
    bid = _bundle(api, seeded)
    ok = api.get(f"/evidence/{bid}/verify").json()
    assert ok["valid"] and ok["root_matches"] and ok["signature_valid"] and ok["simulated_tamper"] is None
    assert ok["anchor"]["status"] in ("not_anchored", "unavailable")  # nothing anchored in this test
    assert ok["tree"]["levels"][-1] == [ok["expected_root"]]
    assert [x["name"] for x in ok["tree"]["leaves"]] == sorted(x["name"] for x in ok["tree"]["leaves"])
    art = ok["tree"]["leaves"][0]["name"]

    bad = api.get(f"/evidence/{bid}/verify?tamper={art}", headers=api.as_("demo1")).json()  # read-only key can demo it
    assert not bad["valid"] and not bad["root_matches"] and bad["simulated_tamper"] == art
    f = bad["failures"][0]
    assert f["artifact"] == art and f["reason"] == "hash_mismatch" and f["expected"] != f["found"]
    assert bad["tree"]["levels"][-1] != [bad["expected_root"]]  # the drawn root changes too

    assert api.get(f"/evidence/{bid}/verify").json()["valid"]  # "Restore": the stored bytes were never modified
    assert api.get(f"/evidence/{bid}/verify?tamper=../../etc/passwd").status_code == 422


def test_benchmark_reports_every_backend_with_gap_and_formulation_and_is_cached(api, seeded):
    b = api.get(f"/campaigns/{seeded}/benchmark?k=3", headers=api.as_("demo1")).json()  # GET: the demo key can run it
    assert b["cached"] is False and {r["backend"] for r in b["rows"]} == {"cpsat", "qaoa", "annealing", "greedy", "bruteforce"}
    cp = next(r for r in b["rows"] if r["backend"] == "cpsat")
    assert cp["gap_vs_cpsat_pct"] == 0.0
    for r in b["rows"]:
        assert r["valid"] is False or r["gap_vs_cpsat_pct"] >= 0  # nobody beats the optimum; losses are shown
    f = b["formulation"]
    assert f["qubo_variables"] == f["qubit_count"] >= 1 and f["reduction"]["original_nodes"] >= f["qubo_variables"]
    assert "not about speed" in b["framing"]
    again = api.get(f"/campaigns/{seeded}/benchmark?k=3").json()
    assert again["cached"] is True and again["computed_at"] == b["computed_at"]


def test_ledger_events_are_the_orgs_own(api, seeded, db):
    import sqlalchemy as sa
    db.execute(sa.text("insert into ledger_events (org_id, kind, tx_hash, subject) values "
                       "(1, 'campaign_published', '0xaa', 's1'), (2, 'attested', '0xbb', 's2')"))
    mine = api.get("/ledger/events").json()["items"]
    assert [e["tx_hash"] for e in mine] == ["0xaa"]
    assert [e["tx_hash"] for e in api.get("/ledger/events", headers=api.as_("org2")).json()["items"]] == ["0xbb"]


def test_metrics_report_is_the_measured_file(api):
    r = api.get("/metrics/report").json()
    assert "triage_threshold_options" in r or "unavailable" in r


def test_status_is_one_batched_poll_with_component_states(api, seeded):
    s = api.get("/status", headers=api.as_("demo1")).json()
    assert s["org"] == {"slug": "org1", "name": "Bank One SOC", "category": "banking"} and s["key_kind"] == "demo"
    assert set(s["components"]) == {"ct", "triage", "confirm", "enrich", "graph", "interdiction", "evidence",
                                    "ledger", "email"}
    assert all(c["status"] in ("ok", "degraded", "failed") and c["detail"] for c in s["components"].values())
    assert s["metrics"]["campaigns_active"] == 1 and "candidates_last_hour" in s["metrics"]
    assert {"regions", "endpoints"} <= set(s["health"])


def test_scaling_benchmark_flags_every_extrapolated_value(api):
    s = api.get("/scaling", headers=api.as_("demo1")).json()
    if "unavailable" in s:
        pytest.skip(s["unavailable"])
    assert s["k_rule"] == "n/4" and [p["n"] for p in s["points"]] == [10, 15, 20, 25, 30, 40, 60, 80]
    for p in s["points"]:
        assert p["bruteforce_extrapolated"] == (p["n"] > 22) and p["k"] == max(2, p["n"] // 4)
        assert p["cpsat_status"] in ("OPTIMAL", "FEASIBLE") and p["plans_log2"] > 0
        if not p["bruteforce_extrapolated"]:
            assert p["coverage"]["bruteforce"] == p["coverage"]["cpsat"]  # exhaustive proves CP-SAT optimal
    t = s["thresholds"]
    assert t["one_second"]["n"] < t["one_hour"]["n"] < t["one_year"]["n"]


def test_benchmark_has_an_exhaustive_row_that_proves_the_optimum(api, seeded):
    import math
    b = api.get(f"/campaigns/{seeded}/benchmark?k=3").json()
    bf = next(r for r in b["rows"] if r["backend"] == "bruteforce")
    if bf["valid"]:
        cp = next(r for r in b["rows"] if r["backend"] == "cpsat")
        assert bf["domains_covered"] == cp["domains_covered"]  # the exhaustive optimum = CP-SAT's answer
        assert bf["subsets_checked"] == math.comb(b["n_after_exact_reduction"], min(3, b["n_after_exact_reduction"]))
        assert b["n_after_exact_reduction"] <= b["n_targetable"]
    else:
        assert bf["error"].startswith("skipped")
