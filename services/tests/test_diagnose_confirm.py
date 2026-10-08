"""B1: the unreachable cause classifier maps every stored verdict detail to one named cause."""
import pytest

from scripts.diagnose_confirm import cause


@pytest.mark.parametrize("detail,want", [
    ("HTTP 404; parked or error page — still a candidate", "HTTP 404 error page"),
    ("HTTP 200; parked or error page — still a candidate", "parked page (HTTP 2xx/3xx)"),
    ("HTTP 502; parked or error page — still a candidate", "HTTP 5xx error page (502)"),
    ("HTTP 403; hosting provider's phishing interstitial hides the page — still a candidate",
     "hosting provider phishing interstitial"),
    ("could not fetch: dns: gone.top does not resolve (gaierror) — still a candidate", "dns: name does not resolve"),
    ("could not fetch: blocked: x.top resolves to a non-public address — still a candidate",
     "ssrf guard: non-public address"),
    ("could not fetch: playwright: Page.goto: Timeout 15000ms exceeded. — still a candidate", "timeout"),
    ("could not fetch: playwright: Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR at https://a/", "tls / http protocol error"),
    ("could not fetch: playwright: Page.goto: net::ERR_TOO_MANY_REDIRECTS at https://a/", "redirect loop"),
    ("could not fetch: ConnectError: [Errno 11001] getaddrinfo failed — still a candidate",
     "dns: name does not resolve"),
])
def test_cause(detail, want):
    assert cause(detail) == want


def test_favicon_census_counts_own_brand_and_any_brand_matches():
    from scripts.diagnose_confirm import favicon_census
    refs = {"Meesho": {"111"}, "ICICI Bank": {"222", "333"}}
    pages = [("Meesho", "111"), ("Meesho", "222"), ("ICICI Bank", "999"), ("Paytm", None)]
    assert favicon_census(pages, refs) == {"pages_with_favicon": 3, "own_brand_match": 1, "any_brand_match": 2,
                                           "reference_brands": 2, "reference_hashes": 3}


def test_strong_signals_are_counted_by_detector():
    from scripts.diagnose_confirm import strong_by_name
    lists = [[{"name": "a", "strength": "strong"}, {"name": "b", "strength": "moderate"}],
             [{"name": "a", "strength": "strong"}, {"name": "c", "strength": "strong"}], None]
    assert strong_by_name(lists) == {"a": 2, "c": 1}


def test_s1_s2_census_counts_domains_by_strength_and_s2_destinations():
    """S4 'which signals fired': S2 ships moderate, so a strong-only count cannot show it firing."""
    from scripts.diagnose_confirm import s1_s2_census
    lists = [[{"name": "credential_post_foreign_origin_js", "strength": "moderate", "artifacts": ["endpoint:shopifysvc.com"]}],
             [{"name": "credential_post_foreign_origin_js", "strength": "moderate", "artifacts": ["endpoint:mydukaan.io"]},
              {"name": "credential_post_foreign_origin_js", "strength": "moderate", "artifacts": ["endpoint:mydukaan.io"]}],
             [{"name": "issuer_is_free_ca", "strength": "weak"}], None]
    assert s1_s2_census(lists) == {"S1_domains": {}, "S2_domains": {"moderate": 2},
                                   "S2_destination_sites": {"shopifysvc.com": 1, "mydukaan.io": 1}}
