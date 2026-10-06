# Data manifest

Free does not mean unattributed (DATA.md §8). Every file under `data/`, where it came from, and when.

| File | Source | Fetched | Notes |
|---|---|---|---|
| `allowlist.txt` (git-ignored, regenerate with `python -m scripts.fetch_allowlist`) | Tranco research list, KU Leuven — https://tranco-list.eu, list ID **56WKN** | 2026-10-06T13:50Z | Top 100,000 rows → 99,627 registrable domains after PSL normalisation (bare public suffixes dropped). |
| `brands.yaml` | Hand-curated, 40 Indian brands, 50 legit domains | 2026-10-06 | Every legit domain DNS-verified by `python -m scripts.verify_brands` (NS/A/SOA exists). DNS existence is not proof of ownership; each was chosen as the brand's well-known public domain. No unverified entries. Not included: the newer `<bank>.bank.in` domains — `bank.in` (RBI/IDRBT-restricted registry) is allowlisted as a zone instead. |
| `shared_hosting.txt` | Hand-curated | 2026-10-06 | Subdomain-hosting platforms present in Tranco but missing from the PSL private section; treated as public suffixes so phishing subdomains on them are never allowlisted. |
| `certstream/config.yaml` | certstream-server-go v1.10.1 sample config, adapted | 2026-10-06 | Self-hosted CT aggregator (spec D8). |
| `capture.jsonl` (git-ignored) | Certificate Transparency logs (RFC 6962 + static-ct tiled) via self-hosted certstream-server-go | 2026-10-06 | 30-minute capture; replay source. Per-operator volume in `reports/ct_capture/`. |

## Enrichment sources (queried live, nothing stored here)

| Source | Use | Notes |
|---|---|---|
| DNS via 1.1.1.1 / 8.8.8.8 (dnspython) | A, AAAA, NS, MX, TXT | |
| RDAP — https://rdap.org (ICANN/IANA bootstrap) | registrar, registrar abuse contact, registration date | preferred over WHOIS (DATA.md §2) |
| Team Cymru IP-to-ASN over DNS | ASN, AS name, country | **Used instead of pyasn**: pyasn needs Microsoft Visual C++ Build Tools to compile on Windows (install failed 2026-10-06). Both are listed in DATA.md §2. |
| TLS handshake (stdlib `ssl`) | served certificate PEM, issuer | |
| Playwright Chromium 131 headless shell | rendered DOM, full-page screenshot | httpx fallback → partial bundle |

## Attribution
Certificate Transparency — RFC 6962 / C2SP static-ct-api, logs operated by Google, Cloudflare, Let's Encrypt, DigiCert, Sectigo, TrustAsia, Geomys, IPng Networks and others · certstream-server-go — d-Rickyy-b (MIT) · Tranco — KU Leuven · Public Suffix List — Mozilla (via tldextract snapshot)
