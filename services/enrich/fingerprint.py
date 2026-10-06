"""Page fingerprints. dom_structure_hash is THE kit fingerprint and the strongest campaign-graph edge.

Stdlib html.parser only: tolerant of malformed markup, no network, no JS.
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

import mmh3

VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
                  "source", "track", "wbr"})
RAW_TEXT = frozenset({"script", "style"})


class _Structure(HTMLParser):
    """Tag names and nesting only: text, attributes, comments and script/style bodies are dropped."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.out.append(f"<{tag}/>" if tag in VOID else f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        self.out.append(f"<{tag}/>" if tag in VOID else f"<{tag}></{tag}>")

    def handle_endtag(self, tag):
        if tag not in VOID:
            self.out.append(f"</{tag}>")


def dom_structure_hash(html: str) -> str:
    """Two pages from the same phishing kit hash identically even with different brand names,
    strings, colours and image URLs. Changing the tag tree changes the hash."""
    p = _Structure()
    try:
        p.feed(html or "")
        p.close()
    except Exception:  # html.parser is tolerant; anything left is still a usable prefix
        pass
    return hashlib.sha256("".join(p.out).encode("utf-8")).hexdigest()


@dataclass
class Form:
    action_url: str
    method: str
    has_password: bool


class _Forms(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.forms: list[Form] = []
        self._open: Form | None = None
        self.title: str | None = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "form":
            action = a.get("action", "").strip()
            self._open = Form(urljoin(self.base, action) if action else self.base,
                              (a.get("method") or "get").lower(), False)
            self.forms.append(self._open)
        elif tag == "input" and a.get("type", "").lower() == "password" and self._open is not None:
            self._open.has_password = True
        elif tag == "title" and self.title is None:
            self._in_title = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "form":
            self._open = None
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or "") + data


def _parse(html: str, base_url: str) -> _Forms:
    p = _Forms(base_url)
    try:
        p.feed(html or "")
        p.close()
    except Exception:
        pass
    return p


def extract_forms(html: str, base_url: str) -> list[Form]:
    return _parse(html, base_url).forms


def page_title(html: str) -> str | None:
    t = _parse(html, "about:blank").title
    return t.strip() if t and t.strip() else None


def favicon_hash(data: bytes) -> str:
    """mmh3 over base64 (newline-wrapped, as Python's encodebytes) — the Shodan convention."""
    return str(mmh3.hash(base64.encodebytes(data)))


def js_bundle_hashes(scripts: list[bytes]) -> list[str]:
    return sorted(hashlib.sha256(s).hexdigest() for s in scripts)
