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
