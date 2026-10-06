"""Enrichment: DNS, RDAP, ASN (Team Cymru via DNS), TLS chain. These attributes become graph EDGES.

Each enricher fails independently: a failure leaves its fields None, records the error, and sets
partial=True. One slow registry never sinks the record (TRD §3, DATA.md §2).
ASN source: Team Cymru IP-to-ASN over DNS (DATA.md §2). pyasn needs MSVC to build on Windows.
"""
from __future__ import annotations

import asyncio
import ssl
from dataclasses import dataclass, field
from datetime import datetime

import dns.asyncresolver
import httpx

from services.config import SETTINGS
from services.enrich.fetch import FetchedPage
from services.enrich.fingerprint import dom_structure_hash, favicon_hash, js_bundle_hashes, page_title
from services.ingest.brands import etld1

RESOLVERS = ["1.1.1.1", "8.8.8.8"]
DNS_TIMEOUT_S = 5.0


@dataclass
class Enrichment:
    ip_addresses: list[str] = field(default_factory=list)
    asn: int | None = None
    asn_name: str | None = None
    country: str | None = None
    nameservers: list[str] = field(default_factory=list)
    mx_records: list[str] = field(default_factory=list)
    cert_issuer: str | None = None
    cert_pem: str | None = None
    registrar: str | None = None
    abuse_email: str | None = None
    registered_at: datetime | None = None
    dom_hash: str | None = None
    favicon_hash: str | None = None
    js_hashes: list[str] = field(default_factory=list)
    page_title: str | None = None
    partial: bool = False
    errors: dict[str, str] = field(default_factory=dict)
    raw: dict = field(default_factory=dict)  # dns / rdap / asn documents for the evidence bundle


def _resolver() -> dns.asyncresolver.Resolver:
    r = dns.asyncresolver.Resolver(configure=False)
    r.nameservers = RESOLVERS
    r.lifetime = DNS_TIMEOUT_S
    return r


async def dns_records(name: str) -> dict:
    r = _resolver()
    out: dict[str, list[str]] = {}
    for rtype in ("A", "AAAA", "NS", "MX", "TXT"):
        try:
            ans = await r.resolve(name if rtype != "NS" else etld1(name), rtype)
            out[rtype] = sorted(x.to_text().rstrip(".").strip('"') for x in ans)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            out[rtype] = []
    return out


def _vcard(entity: dict, key: str) -> str | None:
    for item in (entity.get("vcardArray") or [None, []])[1]:
        if item and item[0] == key:
            return item[3]
    return None


def parse_rdap(doc: dict) -> dict:
    registrar = abuse = None
    for ent in doc.get("entities") or []:
        if "registrar" in (ent.get("roles") or []):
            registrar = _vcard(ent, "fn")
            for sub in ent.get("entities") or []:
                if "abuse" in (sub.get("roles") or []):
                    abuse = _vcard(sub, "email")
    reg = None
    for ev in doc.get("events") or []:
        if ev.get("eventAction") == "registration":
            try:
                reg = datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                pass
    return {"registrar": registrar, "abuse_email": abuse, "registered_at": reg}


async def rdap(name: str) -> dict:
    async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                 headers={"User-Agent": SETTINGS.user_agent}) as c:
        r = await c.get(f"https://rdap.org/domain/{etld1(name)}")
        r.raise_for_status()
        doc = r.json()
    return {**parse_rdap(doc), "doc": doc}


async def asn_for_ip(ip: str) -> dict:
    """Team Cymru: <reversed-ip>.origin.asn.cymru.com TXT -> 'ASN | prefix | CC | registry | date'."""
    r = _resolver()
    if ":" in ip:
        return {}
    rev = ".".join(reversed(ip.split(".")))
    txt = (await r.resolve(f"{rev}.origin.asn.cymru.com", "TXT"))[0].to_text().strip('"')
    asn_s, prefix, cc = [x.strip() for x in txt.split("|")[:3]]
    asn = int(asn_s.split()[0])
    name_txt = (await r.resolve(f"AS{asn}.asn.cymru.com", "TXT"))[0].to_text().strip('"')
    return {"asn": asn, "asn_name": name_txt.split("|")[-1].strip(), "country": cc or None, "prefix": prefix}


async def tls_chain(name: str) -> dict:
    """Served certificate as PEM (evidence) plus issuer O. Stdlib only.
    The issuer is read from a verified handshake; an unverifiable chain still yields the PEM,
    with issuer None (the CT record already carries the issuer)."""
    def grab() -> dict:
        import socket
        out: dict = {"issuer": None, "pem": None}
        raw = ssl.create_default_context()
        raw.check_hostname = False
        raw.verify_mode = ssl.CERT_NONE  # observe what is served, valid or not
        with socket.create_connection((name, 443), timeout=8) as sock, raw.wrap_socket(sock, server_hostname=name) as t:
            out["pem"] = ssl.DER_cert_to_PEM_cert(t.getpeercert(binary_form=True))
        try:
            with socket.create_connection((name, 443), timeout=8) as sock,                     ssl.create_default_context().wrap_socket(sock, server_hostname=name) as t:
                issuer = dict(x[0] for x in t.getpeercert().get("issuer", ()))
                out["issuer"] = issuer.get("organizationName") or issuer.get("commonName")
                out["not_before"] = t.getpeercert().get("notBefore")
        except ssl.SSLError as exc:
            out["verify_error"] = str(exc)[:200]
        return out
    return await asyncio.to_thread(grab)


async def enrich(domain: str, page: FetchedPage | None) -> Enrichment:
    e = Enrichment()

    async def guard(name, coro):
        try:
            return await coro
        except Exception as exc:  # each enricher fails independently
            e.errors[name] = f"{type(exc).__name__}: {exc}"[:300]
            return None

    dns_r, rdap_r, tls_r = await asyncio.gather(guard("dns", dns_records(domain)), guard("rdap", rdap(domain)),
                                                guard("tls", tls_chain(domain)))
    if dns_r:
        e.ip_addresses = list(dns_r.get("A", [])) + list(dns_r.get("AAAA", []))
        e.nameservers = list(dns_r.get("NS", []))
        e.mx_records = list(dns_r.get("MX", []))
        e.raw["dns"] = dns_r
    if rdap_r:
        e.registrar, e.abuse_email, e.registered_at = rdap_r.get("registrar"), rdap_r.get("abuse_email"), rdap_r.get("registered_at")
        e.raw["rdap"] = rdap_r.get("doc", {})
    if tls_r:
        e.cert_issuer, e.cert_pem = tls_r.get("issuer"), tls_r.get("pem")
    v4 = [ip for ip in e.ip_addresses if ":" not in ip]
    if v4:
        asn_r = await guard("asn", asn_for_ip(v4[0]))
        if asn_r:
            e.asn, e.asn_name, e.country = asn_r.get("asn"), asn_r.get("asn_name"), asn_r.get("country")
            e.raw["asn"] = asn_r
    if page is not None:
        e.dom_hash = dom_structure_hash(page.html)
        e.favicon_hash = favicon_hash(page.favicon) if page.favicon else None
        e.js_hashes = js_bundle_hashes(page.scripts)
        e.page_title = page_title(page.html)
    e.partial = bool(e.errors)
    return e
