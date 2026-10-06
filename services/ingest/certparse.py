"""Certstream message -> CertRecord. Names normalised, deduped, capped (TRD §2)."""
from __future__ import annotations

import ipaddress
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone

SAN_CAP = 200
_ENCODE = json.JSONEncoder(ensure_ascii=False).encode  # reused: json.dumps builds an encoder per call


@dataclass
class CertRecord:
    fingerprint: str
    names: list[str]
    overflow: int
    issuer: str | None
    not_before: datetime | None
    not_after: datetime | None
    serial: str | None
    san_count: int
    seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "certstream"
    # when OUR ingest received it. seen_at is the upstream aggregator's stamp (measured ~14 s earlier, a
    # constant delay inside certstream-server-go): keeping both splits upstream latency from ours.
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_json(self) -> str:
        # Hand-built dict: dataclasses.asdict deep-copies and capped ingest near 2k/s.
        return _ENCODE({
            "fingerprint": self.fingerprint, "names": self.names, "overflow": self.overflow,
            "issuer": self.issuer,
            "not_before": self.not_before.isoformat() if self.not_before else None,
            "not_after": self.not_after.isoformat() if self.not_after else None,
            "serial": self.serial, "san_count": self.san_count,
            "seen_at": self.seen_at.isoformat() if self.seen_at else None,
            "source": self.source,
            "received_at": self.received_at.isoformat() if self.received_at else None,
        })

    @staticmethod
    def from_json(s: str) -> "CertRecord":
        d = json.loads(s)
        for k in ("not_before", "not_after", "seen_at", "received_at"):
            if k in d:
                d[k] = datetime.fromisoformat(d[k]) if d[k] else None
        return CertRecord(**d)


def _decode_label(label: str) -> str:
    if label.startswith("xn--"):
        try:
            return label.encode("ascii").decode("idna")
        except (UnicodeError, ValueError):
            return label  # undecodable punycode stays raw; triage still sees it
    return label


def normalize_name(raw: str) -> str | None:
    """Lowercase, strip wildcard and trailing dot, decode IDNA. None for IPs / empties / single labels."""
    n = (raw or "").strip().lower().rstrip(".")
    while n.startswith("*."):
        n = n[2:]
    if not n:
        return None
    if n[-1].isdigit() or ":" in n:  # an IP literal ends in a digit (no TLD is numeric) or has ':'
        try:
            ipaddress.ip_address(n)
            return None
        except ValueError:
            pass
    if "." not in n:
        return None
    if "xn--" not in n:
        return n
    return ".".join(_decode_label(label) for label in n.split("."))


def _ts(v) -> datetime | None:
    return datetime.fromtimestamp(v, timezone.utc) if isinstance(v, (int, float)) else None


def parse_message(msg: dict, source: str = "certstream") -> CertRecord | None:
    if msg.get("message_type") != "certificate_update":
        return None
    data = msg.get("data") or {}
    leaf = data.get("leaf_cert")
    if not leaf:
        return None
    raw = leaf.get("all_domains") or []
    seen: set[str] = set()
    names: list[str] = []
    for r in raw:
        n = normalize_name(r)
        if n and n not in seen:
            seen.add(n)
            names.append(n)
    return CertRecord(
        fingerprint=leaf.get("sha256") or leaf.get("fingerprint") or "",
        names=names[:SAN_CAP],
        overflow=max(0, len(names) - SAN_CAP),
        issuer=(leaf.get("issuer") or {}).get("O"),
        not_before=_ts(leaf.get("not_before")),
        not_after=_ts(leaf.get("not_after")),
        serial=leaf.get("serial_number"),
        san_count=len(raw),
        seen_at=_ts(data.get("seen")) or datetime.now(timezone.utc),
        source=source,
    )


class SeenFingerprints:
    """LRU set. The same certificate arrives from several CT logs; emit it once."""

    def __init__(self, maxlen: int = 500_000):
        self._d: OrderedDict[str, None] = OrderedDict()
        self._max = maxlen

    def add(self, fp: str) -> bool:
        if fp in self._d:
            self._d.move_to_end(fp)
            return False
        self._d[fp] = None
        if len(self._d) > self._max:
            self._d.popitem(last=False)
        return True
