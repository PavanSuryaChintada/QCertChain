"""Raw headers / .eml -> ParsedEmail. Stdlib `email` only. Never raises: whatever an analyst pastes
yields a result, with every missing header listed in `absent` — absent is recorded, never guessed.
Bodies are read only to extract URLs and are not kept.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from email import message_from_bytes, policy
from email.utils import parsedate_to_datetime

from services.ingest.brands import etld1

TRACKED = ("From", "Reply-To", "Return-Path", "Message-ID", "Authentication-Results", "Received", "DKIM-Signature")
_URL = re.compile(r"https?://[^\s\"'<>()\]]+", re.I)
_AUTH = re.compile(r"\b(spf|dkim|dmarc)\s*=\s*([a-z]+)", re.I)
_RCVD_FROM = re.compile(r"from\s+(\S+)", re.I)
_RCVD_BY = re.compile(r"\bby\s+(\S+)", re.I)
_IP = re.compile(r"\[(\d{1,3}(?:\.\d{1,3}){3}|[0-9a-f:]+:[0-9a-f:]+)\]", re.I)
_ADDR = re.compile(r"[\w.+'-]+@([\w-]+(?:\.[\w-]+)+)")
MAX_URLS = 200


@dataclass
class ParsedEmail:
    from_display: str | None = None
    from_addr: str | None = None
    from_etld1: str | None = None
    reply_to_etld1: str | None = None
    return_path_etld1: str | None = None
    message_id_domain: str | None = None
    auth: dict[str, str] = field(default_factory=lambda: {"spf": "absent", "dkim": "absent", "dmarc": "absent"})
    received: list[dict] = field(default_factory=list)   # oldest hop first
    urls: list[str] = field(default_factory=list)
    link_etld1s: list[str] = field(default_factory=list)
    absent: list[str] = field(default_factory=list)


def _domain_of(text: str | None) -> str | None:
    if not text:
        return None
    m = _ADDR.search(str(text))
    return etld1(m.group(1).lower().rstrip(".")) if m else None


def _first_addr(msg, name: str) -> tuple[str | None, str | None]:
    """(display name, addr-spec), tolerant of malformed encoded words and garbage."""
    try:
        h = msg[name]
        if h is None:
            return None, None
        addrs = getattr(h, "addresses", None)
        if addrs:
            return (addrs[0].display_name or None), (addrs[0].addr_spec or None)
        raw = str(h)
    except Exception:
        raw = msg.get_all(name, [""])[0] if msg.get_all(name) else ""
    m = _ADDR.search(raw or "")
    return None, (m.group(0) if m else None)


def _parse_received(values: list[str]) -> list[dict]:
    hops = []
    for v in reversed(values):  # headers are prepended by each hop: reverse = oldest first
        v = " ".join(str(v).split())
        body, _, date = v.rpartition(";")
        at = None
        try:
            at = parsedate_to_datetime(date.strip()).isoformat() if date.strip() else None
        except (TypeError, ValueError):
            pass
        ip = _IP.search(body or v)
        hops.append({"from_host": (_RCVD_FROM.search(body or v) or [None, None])[1],
                     "by_host": (_RCVD_BY.search(body or v) or [None, None])[1],
                     "ip": ip.group(1) if ip else None, "at": at})
    return hops


def _urls(msg) -> list[str]:
    out: list[str] = []
    try:
        parts = list(msg.walk()) if msg.is_multipart() else [msg]
        for part in parts:
            if part.get_content_maintype() != "text":
                continue
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except LookupError:
                text = payload.decode("utf-8", errors="replace")
            out += [u.rstrip(".,;:!?") for u in _URL.findall(text)]
    except Exception:
        pass
    return list(dict.fromkeys(out))[:MAX_URLS]


def parse_email(raw: str | bytes) -> ParsedEmail:
    p = ParsedEmail()
    data = raw.encode("utf-8", errors="replace") if isinstance(raw, str) else (raw or b"")
    try:
        msg = message_from_bytes(data, policy=policy.default)
    except Exception:
        p.absent = list(TRACKED)
        p.urls = list(dict.fromkeys(_URL.findall(data.decode("utf-8", "replace"))))[:MAX_URLS]
        return p
    present = {k.lower() for k in msg.keys()}
    p.absent = [h for h in TRACKED if h.lower() not in present]

    p.from_display, p.from_addr = _first_addr(msg, "From")
    p.from_etld1 = _domain_of(p.from_addr)
    p.reply_to_etld1 = _domain_of(_first_addr(msg, "Reply-To")[1])
    p.return_path_etld1 = _domain_of(msg.get("Return-Path"))
    p.message_id_domain = _domain_of(msg.get("Message-ID"))

    ar = msg.get_all("Authentication-Results") or []
    if ar:  # the top-most header was added by the receiving MX: trust that one
        found = {k.lower(): v.lower() for k, v in _AUTH.findall(" ".join(str(ar[0]).split()))}
        p.auth = {k: found.get(k, "none") for k in ("spf", "dkim", "dmarc")}
    rspf = msg.get("Received-SPF")
    if rspf and p.auth["spf"] in ("absent", "none"):
        p.auth["spf"] = str(rspf).split()[0].lower()
    p.received = _parse_received(msg.get_all("Received") or [])

    p.urls = _urls(msg)
    if not p.urls and not present:  # body-only paste: the whole text is the body
        p.urls = list(dict.fromkeys(_URL.findall(data.decode("utf-8", "replace"))))[:MAX_URLS]
    hosts = []
    for u in p.urls:
        m = re.match(r"https?://([^/:?#]+)", u, re.I)
        if m:
            hosts.append(etld1(m.group(1).lower()))
    p.link_etld1s = list(dict.fromkeys(hosts))
    return p
