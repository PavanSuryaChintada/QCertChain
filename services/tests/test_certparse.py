import json
from pathlib import Path

from services.ingest.certparse import CertRecord, SeenFingerprints, normalize_name, parse_message

FIX = json.loads((Path(__file__).parent / "fixtures/cert_update.json").read_text(encoding="utf-8"))
CYRILLIC_APPLE = "xn--80ak6aa92e".encode().decode("idna")


def test_wildcards_ips_empties_handled():
    r = parse_message(FIX)
    assert r.names == ["sbi-login.top", f"{CYRILLIC_APPLE}.com", "example.com"]
    assert r.san_count == 6
    assert r.issuer == "Let's Encrypt"
    assert r.fingerprint == FIX["data"]["leaf_cert"]["sha256"]


def test_normalize_edge_cases():
    assert normalize_name("*.A.Example.com.") == "a.example.com"
    assert normalize_name("") is None
    assert normalize_name("10.0.0.1") is None
    assert normalize_name("2001:db8::1") is None
    assert normalize_name("localhost") is None
    assert normalize_name("xn--invalid--.com") == "xn--invalid--.com"


def test_san_cap_200():
    msg = json.loads(json.dumps(FIX))
    msg["data"]["leaf_cert"]["all_domains"] = [f"d{i}.example.org" for i in range(350)]
    r = parse_message(msg)
    assert len(r.names) == 200 and r.overflow == 150


def test_non_cert_message_ignored():
    assert parse_message({"message_type": "heartbeat"}) is None


def test_message_without_leaf_does_not_crash():
    assert parse_message({"message_type": "certificate_update", "data": {}}) is None


def test_json_roundtrip_keeps_unicode_and_dates():
    r = parse_message(FIX, source="replay")
    back = CertRecord.from_json(r.to_json())
    assert back == r and back.source == "replay"


def test_dedup_same_cert_from_two_logs():
    s = SeenFingerprints(maxlen=3)
    assert s.add("a") and not s.add("a")
    for x in "bcd":
        s.add(x)
    assert s.add("a")


def test_parse_and_serialise_fast_enough_for_3000_per_sec():
    """Best of 5 runs (other processes share the CPU). Bar = 2x the 3,000/s ingest target,
    leaving headroom for json decode and the Redis pipeline."""
    import time
    msgs = []
    for i in range(3000):
        m = json.loads(json.dumps(FIX))
        m["data"]["leaf_cert"]["all_domains"] = [f"www.shop{i}.example.com", f"shop{i}.example.com"]
        msgs.append(m)
    best = float("inf")
    for _ in range(5):
        t = time.perf_counter()
        for m in msgs:
            parse_message(m).to_json()
        best = min(best, time.perf_counter() - t)
    rate = len(msgs) / best
    assert rate > 6000, f"{rate:.0f}/s"


def test_record_carries_our_receipt_time_separately_from_ct_seen():
    from datetime import datetime, timezone
    before = datetime.now(timezone.utc)
    r = parse_message(FIX)
    assert r.received_at >= before and r.seen_at != r.received_at
    back = CertRecord.from_json(r.to_json())
    assert back.received_at == r.received_at
