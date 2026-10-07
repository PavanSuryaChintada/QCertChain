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
    assert r.is_candidate and any(x.feature in ("homoglyph_hit", "skeleton_exact") for x in r.reasons)


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
# Bare brand token, no second signal (the double count that once pushed them higher is fixed). At the owner's 0.35
# threshold (decision 1) they ARE candidates: the measured hard-negative cost of 0.35. They are fetched and fail the
# two-strong-signal confirmation gate; triage never accuses them.
HARD_NEGATIVE_AT_035 = ["koersgenootnl.stelvio.growww.today", "etolluat.idfcbank.com"]

REAL_FP = [
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


@pytest.mark.parametrize("d", HARD_NEGATIVE_AT_035)
def test_bare_brand_token_is_a_candidate_at_035_with_exactly_one_signal(d):
    """Owner decision 1: a candidate is not a verdict. A bare token clears 0.35 on its own and carries exactly one
    reason, so the queue shows WHY it is there and confirmation decides."""
    from services.ingest.triage import W_BRAND
    r = triage(d)
    assert r.is_candidate and [x.feature for x in r.reasons] == ["brand_token_exact"] and r.score == W_BRAND


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
    # but real script confusables on a short token still count (now as an exact skeleton match)
    assert any(x.feature in ("homoglyph_hit", "skeleton_exact") for x in triage("ѕbі-kyc-verify.top").reasons)


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


@pytest.mark.parametrize("d", ["xn--cicibank-shh.com", "xn--hdfcbnk-6fg.com", "xn--pytm-53d.com",
                               "xn--flpkart-sog.com", "xn--bi-kyc-hvf.com"])
def test_real_punycode_homographs_are_candidates(d):
    """Review I8, superseded by owner decision 3: a pure homograph used to clear the threshold only because
    lookalike and homoglyph_hit both fired. It is now ONE observation, skeleton_exact (0.75), which clears it on
    its own; a homograph that is only a substring still carries homoglyph_hit."""
    r = triage(d)
    assert r.is_candidate and any(x.feature in ("homoglyph_hit", "skeleton_exact") for x in r.reasons), (d, r.score, r.reasons)


# ---- confusable skeleton (owner decision 3, 2026-10-07): an exact skeleton match is its own ~0.75 signal ----------
@pytest.mark.parametrize("d", ["xn--bi-doc.co.in",        # Cyrillic-s sbi.co.in — SBI's own domain, spoofed
                               "xn--cicibank-shh.com",    # Cyrillic-i icicibank.com
                               "xn--pytm-53d.com",        # Cyrillic-a paytm.com
                               "xn--flpkart-sog.com"])    # Cyrillic-i flipkart.com
def test_exact_skeleton_match_to_a_brand_is_a_candidate_on_its_own(d):
    r = triage(d)
    feats = {x.feature: x for x in r.reasons}
    assert "skeleton_exact" in feats and feats["skeleton_exact"].contribution >= 0.75, r.reasons
    assert r.is_candidate and r.brand is not None
    assert "homoglyph_hit" not in feats and "lookalike" not in feats  # one observation, counted once


def test_skeleton_runs_before_edit_distance():
    """A homoglyph AND a typo: Cyrillic i plus n->m. Neither raw edit distance (2 + non-ASCII) nor the exact skeleton
    sees it; edit distance over skeletons does."""
    r = triage("іcicibamk-login.com".encode("idna").decode())
    assert r.is_candidate and any(x.feature == "lookalike" for x in r.reasons), r.reasons


@pytest.mark.parametrize("d", ["vl.com", "sb1.net", "0nline.com", "ici.org"])
def test_ascii_confusions_on_short_tokens_never_fire_alone(d):
    """l/1/0 confusions on 2-3 letter tokens are everywhere in ordinary names; only non-ASCII homoglyphs (or tokens
    of 5+ characters) count as an exact skeleton match."""
    assert not any(x.feature == "skeleton_exact" for x in triage(d).reasons), triage(d).reasons


def test_brands_own_domains_stay_allowlisted_under_skeleton_matching():
    for d in ("sbi.co.in", "icicibank.com", "paytm.com", "flipkart.com", "onlinesbi.sbi"):
        assert not triage(d).is_candidate, d
