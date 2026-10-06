"""RELEASE GATE (CLAUDE.md §6): known-good never candidates; known phishing always candidates; < 5 ms."""
import time

import pytest

from services.config import SETTINGS
from services.ingest.triage import triage

LEGIT = ["google.com", "sbi.co.in", "hdfcbank.com", "paytm.com", "amazon.in", "icicibank.com",
         "onlinesbi.sbi", "incometax.gov.in", "flipkart.com", "airtel.in", "service.gov.in", "wikipedia.org",
         "www.sbi.co.in", "netbanking.hdfcbank.com", "retail.onlinesbi.sbi", "sbi.bank.in"]
PHISH = ["sbi-verify-kyc.top", "icici-netbanking-login.xyz", "hdfc-secure-update.click",
         "paytm-kyc-verify.buzz", "incometax-refund-verify.top", "login.sbi.co.in.attacker.top",
         "icicibannk-login.top", "yonosbi-update.rest", "sbi-kyc-verify.weebly.com"]


@pytest.mark.parametrize("d", LEGIT)
def test_known_good_never_candidates(d):
    r = triage(d)
    assert not r.is_candidate, (d, r.score, r.reasons)


@pytest.mark.parametrize("d", PHISH)
def test_known_phishing_always_candidates(d):
    r = triage(d)
    assert r.is_candidate, (d, r.score, r.reasons)


def test_allowlist_short_circuits_with_reason():
    r = triage("www.sbi.co.in")
    assert r.score == 0 and [x.feature for x in r.reasons] == ["allowlisted"]


def test_etld1_not_naive_split():
    assert triage("login.sbi.co.in.attacker.top").etld1 == "attacker.top"


def test_homoglyph_cyrillic_is_candidate_with_reason():
    r = triage("ѕbі-kyc-verify.top")  # Cyrillic dze + byelorussian i
    assert r.is_candidate and any(x.feature == "homoglyph_hit" for x in r.reasons)


def test_digit_swap_homoglyph():
    r = triage("a1rtel-kyc-update.top")
    assert r.is_candidate and r.brand == "Airtel"


def test_punycode_input_decoded_and_bad_punycode_safe():
    assert triage("xn--b-6ed6m-kyc-verify.top").score >= 0  # whatever it decodes to, no crash
    assert triage("xn--invalid--.com").score >= 0


def test_short_token_only_matches_whole_segment():
    assert not any(x.feature == "brand_token_exact" for x in triage("service-login.top").reasons)  # 'vi' inside
    assert any(x.feature == "brand_token_exact" for x in triage("vi-recharge-kyc.top").reasons)


def test_lookalike_needs_token_of_5_plus():
    # 'sbx' is 1 edit from 'sbi' but 3-letter tokens never use edit distance
    assert not any(x.feature == "lookalike" for x in triage("sbx-portal.top").reasons)
    r = triage("flipkrat-sale.top")
    assert any(x.feature == "lookalike" and x.value == "flipkart" for x in r.reasons)


def test_free_ca_new_domain_never_fires_in_triage():
    r = triage("sbi-verify-kyc.top", issuer="Let's Encrypt")
    assert not any("new" in x.feature for x in r.reasons)


def test_reasons_sum_to_score_and_provenance():
    for d in PHISH + ["icicibannk-secure-login-update-verify-account.top"]:
        r = triage(d)
        assert r.provenance == "rules" and r.threshold == SETTINGS.triage_threshold
        assert sum(x.contribution for x in r.reasons) == pytest.approx(r.score)
        assert 0 <= r.score <= 1


def test_under_5ms_per_name():
    names = [f"shop{i}-example.com" for i in range(5000)] + PHISH * 100 + [f"cdn{i}.assets-host.net" for i in range(2000)]
    triage("warmup.example")
    t = time.perf_counter()
    for n in names:
        triage(n)
    per = (time.perf_counter() - t) / len(names)
    assert per < 0.005, f"{per * 1000:.3f} ms/name"


# Real false positives from the 2026-10-06 capture. Each reproduces one over-trigger.
REAL_FP = [
    "koersgenootnl.stelvio.growww.today",                       # one hit counted as exact AND lookalike
    "etolluat.idfcbank.com",                                     # same double count
    "bi.1xbet-onlines.top",                                      # common word 2 deletions from 'onlinesbi'
    "dbs-cas-system-cas-ccs-sub-vi0svszw0yo62-alog-system.dog.us-west16-b.s.gpcdemolabs.com",  # hex -> 'vi'
    "s3-accesspoint-fips.us-west-1.amazonaws.com",               # AWS's own domains
    "b-950e4745-28b7-42d8-99c5-292146feb9a9.mq.cn-northwest-1.on.amazonwebservices.com.cn",
    "b-53db99fd-fde6-4f65-aa59-027261f38ff1.mq.eusc-de-east-1.on.amazonwebservices.eu",
]


@pytest.mark.parametrize("d", REAL_FP)
def test_real_capture_false_positives_not_candidates(d):
    r = triage(d)
    assert not r.is_candidate, (d, r.score, r.reasons)


def test_same_token_never_counted_as_exact_and_lookalike():
    feats = [x.feature for x in triage("growww-kyc.top").reasons]
    assert "brand_token_exact" in feats and "lookalike" not in feats


def test_short_token_with_edge_digits_still_matches():
    assert triage("sbi1-kyc-verify.top").is_candidate
    assert triage("2sbi-netbanking.xyz").is_candidate


def test_brand_owned_tld_is_legit():
    for d in ["r-one-jio-loyalty-grafana.api.engageapps.jio", "kyc-verify.onlinesbi.sbi", "login-secure.aws.amazon"]:
        r = triage(d)
        assert not r.is_candidate and r.reasons[0].feature == "allowlisted", (d, r.reasons)


def test_ascii_homoglyph_never_builds_a_short_token():
    # 'vl' -> 'vi' through the l/i class: ASCII-only confusion on a 2-letter token is noise
    assert not any(x.feature == "homoglyph_hit" for x in triage("vl.65515107.xyz").reasons)
    # but real script confusables on a short token still count
    assert any(x.feature == "homoglyph_hit" for x in triage("ѕbі-kyc-verify.top").reasons)


def test_no_single_call_pathologically_slow():
    import time
    names = [f"{'x' * 60}-{i}.{'y' * 60}.example-{i}.com" for i in range(300)]
    worst = 0.0
    for n in names:
        t = time.perf_counter()
        triage(n)
        worst = max(worst, time.perf_counter() - t)
    assert worst < 0.05, f"{worst * 1000:.1f} ms"


def test_unknown_tld_is_scored_not_treated_as_public_suffix():
    # A TLD missing from the PSL snapshot (new gTLD) must still be triaged, not zeroed.
    r = triage("sbi-kyc-verify.notarealtld")
    assert r.is_candidate and r.reasons[0].feature != "public_suffix", r.reasons


def test_bare_public_suffix_name_scores_zero():
    r = triage("s3-accesspoint-fips.us-west-1.amazonaws.com")
    assert r.score == 0 and r.reasons[0].feature == "public_suffix"


def test_warm_loads_everything_up_front():
    import time
    from services.ingest.triage import warm
    warm()
    t = time.perf_counter()
    triage("first-real-call-after-warm.com")
    assert time.perf_counter() - t < 0.05
