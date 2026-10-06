import pytest

from services.enrich import enrichers
from services.enrich.enrichers import Enrichment, enrich, parse_rdap


async def test_one_failing_enricher_marks_partial_not_fatal(monkeypatch):
    async def ok_dns(name):
        return {"A": ["203.0.113.9"], "AAAA": [], "NS": ["ns1.cheapdns.top"], "MX": [], "TXT": []}

    async def bad_rdap(name):
        raise TimeoutError("rdap.org timed out")

    async def ok_asn(ip):
        return {"asn": 64500, "asn_name": "EXAMPLE-AS", "country": "NL"}

    async def ok_tls(name):
        return {"issuer": "Let's Encrypt", "pem": "-----BEGIN CERTIFICATE-----"}

    monkeypatch.setattr(enrichers, "dns_records", ok_dns)
    monkeypatch.setattr(enrichers, "rdap", bad_rdap)
    monkeypatch.setattr(enrichers, "asn_for_ip", ok_asn)
    monkeypatch.setattr(enrichers, "tls_chain", ok_tls)
    e = await enrich("icici-verify-kyc.top", page=None)
    assert isinstance(e, Enrichment) and e.partial
    assert "rdap" in e.errors and e.registrar is None
    assert e.ip_addresses == ["203.0.113.9"] and e.asn == 64500 and e.nameservers == ["ns1.cheapdns.top"]
    assert e.cert_issuer == "Let's Encrypt"


async def test_all_ok_not_partial(monkeypatch):
    async def ok(*a):
        return {}
    for f in ("dns_records", "rdap", "asn_for_ip", "tls_chain"):
        monkeypatch.setattr(enrichers, f, ok)
    e = await enrich("x.top", page=None)
    assert not e.partial and e.errors == {}


def test_parse_rdap_registrar_abuse_and_dates():
    doc = {"events": [{"eventAction": "registration", "eventDate": "2026-10-03T08:00:00Z"}],
           "entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["fn", {}, "text", "NameSilo, LLC"]]],
                         "entities": [{"roles": ["abuse"], "vcardArray": ["vcard", [["email", {}, "text", "abuse@namesilo.com"]]]}]}]}
    r = parse_rdap(doc)
    assert r["registrar"] == "NameSilo, LLC" and r["abuse_email"] == "abuse@namesilo.com"
    assert r["registered_at"].isoformat().startswith("2026-10-03")


def test_parse_rdap_tolerates_garbage():
    assert parse_rdap({}) == {"registrar": None, "abuse_email": None, "registered_at": None}


@pytest.mark.network
async def test_real_dns_example_com():
    r = await enrichers.dns_records("example.com")
    assert r["A"]


@pytest.mark.network
async def test_real_tls_chain_example_com_without_new_dependencies():
    r = await enrichers.tls_chain("example.com")
    assert r["pem"].startswith("-----BEGIN CERTIFICATE-----") and r["issuer"]
