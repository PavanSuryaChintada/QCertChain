from services.config import SETTINGS
from services.ingest.brands import load_allowlist, load_brands


def test_brands_shape():
    idx = load_brands(SETTINGS.brands_file)
    assert len(idx.brands) >= 40
    assert {"sbi.co.in", "hdfcbank.com", "icicibank.com", "paytm.com", "incometax.gov.in"} <= idx.legit_etld1s
    assert all(b.tokens and b.sector and b.legit_domains for b in idx.brands)


def test_tokens_unique_across_brands():
    idx = load_brands(SETTINGS.brands_file)
    tokens = [t for b in idx.brands for t in b.tokens]
    assert len(tokens) == len(set(tokens))
    assert all(t == t.lower() and t.isalnum() for t in tokens)


def test_by_token_and_length_buckets():
    idx = load_brands(SETTINGS.brands_file)
    assert idx.by_token["sbi"].name == "State Bank of India"
    assert "icicibank" in idx.tokens_by_len[len("icicibank")]


def test_legit_etld1s_use_public_suffix_list():
    idx = load_brands(SETTINGS.brands_file)
    # gov.in is a public suffix, so the registrable domain keeps the label
    assert "incometax.gov.in" in idx.legit_etld1s and "gov.in" not in idx.legit_etld1s


def test_allowlist_contains_every_legit_domain():
    idx = load_brands(SETTINGS.brands_file)
    allow = load_allowlist(SETTINGS.allowlist_file, idx)
    assert idx.legit_etld1s <= allow
    assert "google.com" in allow and len(allow) >= 99_000  # 100k Tranco rows; bare suffixes dropped, dupes collapse
    assert "github.io" not in allow  # a public suffix: attackers' subdomains there are their own eTLD+1


def test_shared_hosting_subdomains_are_their_own_registrable_domain():
    from services.ingest.brands import etld1
    for host in ["sbi-kyc-verify.weebly.com", "hdfc-login.000webhostapp.com", "icici.surge.sh",
                 "x.godaddysites.com", "paytm-kyc.github.io"]:
        assert etld1(host) == host, host


def test_shared_hosting_subdomain_not_allowlisted_even_though_platform_is_in_tranco():
    from services.ingest.brands import etld1
    idx = load_brands(SETTINGS.brands_file)
    allow = load_allowlist(SETTINGS.allowlist_file, idx)
    assert etld1("sbi-kyc-verify.weebly.com") not in allow
    assert "weebly.com" not in allow
