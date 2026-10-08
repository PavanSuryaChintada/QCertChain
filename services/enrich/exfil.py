"""Credential-exfiltration signals for JavaScript-era phishing kits (S1, S2). Static inspection only.

Measured on the live feed (2026-10-07): 0 of 427 live candidates produced a single strong signal. Modern kits are
JS single-page apps: the login form is built in the browser and credentials leave by fetch/XHR, so the raw-HTML
"form action points elsewhere" check cannot fire (meesho-all.cfd has no <form> element at all). These signals read
what the kit itself ships: the rendered DOM and its JavaScript.

Both require a password or OTP input in the RENDERED DOM. Nothing is typed, clicked or submitted, ever.

  S1 exfil_endpoints       a hardcoded exfiltration endpoint: a Telegram bot API URL WITH a bot token, a Discord
                           webhook, or a mail-sending / form-relay API. A bare t.me link or share button never fires.
  S2 foreign_post_endpoints a POST written in the page's code (fetch, XHR, axios, jQuery, sendBeacon) to a site that
                           is neither the page's own eTLD+1, the impersonated brand's, nor a listed analytics /
                           captcha / error-reporting service. Requests the page fires while LOADING do not count:
                           on the S3 gate they were analytics and telemetry on 5 of 6 legitimate login pages.

Independence: these functions report what they see. That one observation (a POST to api.telegram.org seen by both
S1 and S2) counts as ONE strong signal is enforced once, for every signal, in confirm.independent_strong.

Limits, stated: URLs assembled at runtime from variables, or posted to the page's own origin and relayed server-side,
are not seen. Handlers are read from shipped code, not resolved through framework internals.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from services.ingest.brands import etld1

_PASSWORD = re.compile(r"<input\b[^>]*\btype\s*=\s*[\"']?password", re.I)
_OTP = re.compile(r"<input\b[^>]*(?:autocomplete\s*=\s*[\"']?one-time-code|"
                  r"\b(?:name|id|placeholder|aria-label)\s*=\s*[\"'][^\"']*\b(?:otp|one[- ]time)\b)", re.I)


def credential_input(html: str) -> bool:
    """A password or one-time-code input in the rendered DOM (an input element, not text about one)."""
    return bool(_PASSWORD.search(html) or _OTP.search(html))


@dataclass(frozen=True)
class Hit:
    kind: str
    match: str      # the matched text, as evidence
    where: str      # script URL, "inline#n", "rendered DOM" or "network: ..."
    origin: str = ""


_TG_TOKEN = r"\d{6,12}:[A-Za-z0-9_-]{30,}"
S1_PATTERNS = (
    ("telegram_bot", re.compile(rf"api\.telegram\.org/bot{_TG_TOKEN}/send(?:Message|Document|Photo)", re.I)),
    ("discord_webhook", re.compile(r"discord(?:app)?\.com/api/webhooks/\d{15,20}/[A-Za-z0-9_-]{10,}", re.I)),
    ("mail_api", re.compile(r"api\.mailgun\.net/v3/|api\.sendgrid\.com/v3/mail/send|api\.emailjs\.com/api/v1\.0/email"
                            r"|api\.(?:brevo|sendinblue)\.com/v3/smtp/email|api\.smtp2go\.com/v3/email", re.I)),
    ("form_relay", re.compile(r"formspree\.io/f/\w+|getform\.io/f/\w+|formsubmit\.co/(?:ajax/)?[\w@.-]+"
                              r"|submit-form\.com/\w+|usebasin\.com/f/\w+", re.I)),
)
_TG_PARTS = (re.compile(r"api\.telegram\.org/bot", re.I), re.compile(rf"\b{_TG_TOKEN}\b"),
             re.compile(r"send(?:Message|Document|Photo)"))


def _sources(html: str, scripts: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [("rendered DOM", html), *scripts]


def exfil_endpoints(html: str, scripts: list[tuple[str, str]]) -> list[Hit]:
    """S1. `scripts` = (where, source text). Empty unless the rendered DOM asks for a credential."""
    if not credential_input(html):
        return []
    hits: dict[tuple[str, str], Hit] = {}
    for where, text in _sources(html, scripts):
        for kind, rx in S1_PATTERNS:
            for m in rx.finditer(text):
                hits.setdefault((kind, m.group(0)), Hit(kind, m.group(0), where))
        if not any(k == "telegram_bot" for k, _ in hits) and all(p.search(text) for p in _TG_PARTS):
            tok = _TG_PARTS[1].search(text).group(0)
            hits.setdefault(("telegram_bot", tok), Hit("telegram_bot", f"api.telegram.org/bot + {tok} + send*", where))
    return list(hits.values())


# ---- S2 --------------------------------------------------------------------------------------------------------
_Q = r"[\"'`]"
_URL = rf"{_Q}(https?://[^\"'`\s]+){_Q}"
S2_CALLS = (
    re.compile(rf"\bfetch\(\s*{_URL}\s*,\s*\{{[^}}]{{0,400}}?\bmethod\s*:\s*{_Q}POST{_Q}", re.I | re.S),
    re.compile(rf"\baxios\.post\(\s*{_URL}", re.I),
    re.compile(rf"\$\.post\(\s*{_URL}", re.I),
    re.compile(rf"\.open\(\s*{_Q}POST{_Q}\s*,\s*{_URL}", re.I),
    re.compile(rf"\bsendBeacon\(\s*{_URL}", re.I),
)
_AJAX = re.compile(r"\$\.ajax\(\s*\{([^}]{0,600})\}", re.I | re.S)
_AJAX_URL = re.compile(rf"\burl\s*:\s*{_URL}", re.I)
_AJAX_POST = re.compile(rf"\b(?:type|method)\s*:\s*{_Q}POST{_Q}", re.I)

# Third parties a legitimate login page posts to on its own (analytics, captcha, error reporting, consent).
# Kept short and named: anything not here that receives a POST from a credential page is evidence.
BENIGN_SITES = frozenset({
    "google-analytics.com", "googletagmanager.com", "google.com", "gstatic.com", "recaptcha.net", "hcaptcha.com",
    "doubleclick.net", "cloudflare.com", "cloudflareinsights.com", "sentry.io", "hotjar.com", "hotjar.io",
    "clarity.ms", "segment.io", "segment.com", "mixpanel.com", "amplitude.com", "nr-data.net", "newrelic.com",
    "datadoghq.com", "datadoghq-browser-agent.com", "bing.com", "facebook.com", "facebook.net", "linkedin.com",
    "onetrust.com", "cookielaw.org", "branch.io", "onesignal.com", "adobedtm.com", "omtrdc.net", "demdex.net",
})


_HOST = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def _site(url: str) -> str:
    """eTLD+1 of a real public hostname, else "" ("https://www." or "https://localhost/" is not a destination)."""
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".") if "://" in url else url.split("/")[0].lower()
    except ValueError:
        return ""
    return etld1(host) if _HOST.match(host) else ""


def _origin(url: str) -> str:
    u = urlsplit(url)
    return f"{u.scheme}://{u.hostname}" + (f":{u.port}" if u.port else "")


def foreign_post_endpoints(html: str, scripts: list[tuple[str, str]], page_url: str,
                           legit_sites: set[str]) -> list[Hit]:
    """S2. POSTs written in the rendered DOM's inline code and in the page's scripts; one Hit per destination."""
    if not credential_input(html):
        return []
    own = _site(page_url)
    ok = {own, *legit_sites, *BENIGN_SITES}
    found: list[tuple[str, str]] = []  # (url, where)
    for where, text in _sources(html, scripts):
        for rx in S2_CALLS:
            found += [(m.group(1), where) for m in rx.finditer(text)]
        for m in _AJAX.finditer(text):
            u = _AJAX_URL.search(m.group(1))
            if u and _AJAX_POST.search(m.group(1)):
                found.append((u.group(1), where))
    hits: dict[str, Hit] = {}
    for url, where in found:
        if _site(url) and _site(url) not in ok:
            hits.setdefault(_origin(url), Hit("credential_post_foreign_origin_js", url, where, _origin(url)))
    return list(hits.values())
