# DATA — SEVER

Every source here is free, public, and needs no approval. Nothing in this project requires a paid feed, a partner agreement, or real customer data.

---

## 1. Certificate Transparency — the primary source

### certstream (public aggregator)

```
wss://certstream.calidog.io/
```

No API key. No rate limit. ~200,000 certificates per minute.

```python
import websockets, json

async with websockets.connect("wss://certstream.calidog.io/") as ws:
    async for raw in ws:
        msg = json.loads(raw)
        if msg.get("message_type") != "certificate_update":
            continue
        data = msg["data"]
        names = data["leaf_cert"]["all_domains"]     # the SANs
        issuer = data["leaf_cert"]["issuer"]["O"]
        not_before = data["leaf_cert"]["not_before"]
```

**Do this on day 0, before anything else:** run the connection and pipe 30 minutes to `data/capture.jsonl`. That file is your replay source and your demo insurance. The public endpoint goes down periodically and you will not want to discover that at hour 34.

```bash
python -m services.ingest.capture --minutes 30 --out data/capture.jsonl
```

### Fallback aggregators

If calidog is down, these speak similar protocols:

- `wss://certstream.cloudflare.com/` *(if available)*
- **Direct CT log polling** via the RFC 6962 `get-entries` API. Slower and more work, but no dependency on an aggregator. Known logs: Google Argon/Xenon, Cloudflare Nimbus, Let's Encrypt Oak.
- `crt.sh` — searchable CT database, good for seeding historical campaigns, **not** for real-time.

---

## 2. Enrichment sources

| Source | What it gives | Access |
|---|---|---|
| **DNS** (`dnspython`) | A, AAAA, NS, MX, TXT | Direct, use 1.1.1.1 / 8.8.8.8 |
| **WHOIS** (`python-whois`) | Registrar, creation date, registrant | Free, **heavily rate-limited** |
| **RDAP** | Structured WHOIS replacement | `https://rdap.org/domain/{name}` — JSON, no key, **prefer this over WHOIS** |
| **ASN lookup** (`pyasn`) | ASN, netblock, country | Offline dataset, download once |
| **Team Cymru** | ASN via DNS | `dig +short AS{ip}.origin.asn.cymru.com TXT` |
| **TLS chain** | Issuer, validity, SANs as served | Python `ssl` module direct |
| **Page fetch** | DOM, screenshot, headers | Playwright, `httpx` fallback |

**Use RDAP, not WHOIS, wherever possible.** It returns JSON, it is not rate-limited into uselessness, and it does not require parsing free-text that differs per registrar.

**pyasn setup** — do this once at the start, it takes a few minutes and then works offline forever:
```bash
pyasn_util_download.py --latest
pyasn_util_convert.py --single rib.*.bz2 data/ipasn.dat
```

---

## 3. Known-phishing corpora — for validation, not detection

These tell you whether your triage is any good. They are **not** the detection mechanism — they lag by hours to days, which is the whole problem we are solving.

| Source | Use |
|---|---|
| **OpenPhish** — `openphish.com/feed.txt` | Free community feed, updated frequently |
| **PhishTank** — `phishtank.org` | Community-verified, free API with registration |
| **URLhaus** — `urlhaus.abuse.ch` | Malware URLs, free API |
| **Tranco** — `tranco-list.eu` | Top-1M domains — **this is your allowlist base** |

**Validation method:** take confirmed OpenPhish entries from the last 24 hours, look up when their certificate appeared in CT, and measure the gap. **That gap is your headline number.** Compute it and put it on a slide — it is far stronger than a claim.

---

## 4. Brand list — `data/brands.yaml`

~40 Indian brands, hand-curated. This drives triage.

```yaml
- name: State Bank of India
  tokens: [sbi, onlinesbi, yonosbi]
  legit_domains: [sbi.co.in, onlinesbi.sbi, yonosbi.com]
  sector: banking

- name: HDFC Bank
  tokens: [hdfc, hdfcbank, netbanking]
  legit_domains: [hdfcbank.com, hdfc.com]
  sector: banking

- name: Paytm
  tokens: [paytm, paytmbank]
  legit_domains: [paytm.com, paytmbank.com]
  sector: fintech

- name: Income Tax India
  tokens: [incometax, itrfiling, efiling]
  legit_domains: [incometax.gov.in, incometaxindia.gov.in]
  sector: government
```

**Cover:** SBI, HDFC, ICICI, Axis, Kotak, PNB, BoB · Paytm, PhonePe, GPay, UPI, BHIM · Jio, Airtel, Vi · Income Tax, EPFO, Aadhaar/UIDAI, DigiLocker, IRCTC, India Post · Amazon.in, Flipkart, Myntra · Zerodha, Groww, Upstox.

**Government and tax brands matter most.** Those campaigns spike around filing deadlines and they target people with the least technical defence.

---

## 5. Allowlist — `data/allowlist.txt`

Tranco top 100k, plus every `legit_domains` entry from brands.yaml, plus common CDN and infrastructure domains.

```bash
curl -sL https://tranco-list.eu/top-1m.csv.zip -o /tmp/t.zip
unzip -p /tmp/t.zip | head -100000 | cut -d, -f2 > data/allowlist.txt
```

**Checked first, before any scoring.** A domain on the allowlist scores zero and exits immediately. `sbi.co.in` must never become a candidate.

---

## 6. Seeding the demo campaign

You need a 400-domain campaign that clusters correctly. Two ways:

**Preferred — real.** Pull confirmed phishing URLs from OpenPhish, group by shared hosting IP via DNS, take the largest cluster. Real domains, real infrastructure, real links. If you can get 50+ real domains sharing a kit, use them.

**Fallback — synthetic.** Generate 400 domains across 12 IPs, 3 ASNs, 4 nameservers, 1 kit hash, with realistic naming. **Label it `source: seed` in the database and say so on screen.**

```bash
python -m services.api.seed --campaign titli-kit --domains 400 --ips 12 --asns 3 --ns 4
```

**Never present synthetic data as live.** The `source` column exists for this and the UI must show it.

---

## 7. Prompt for Claude Code

Paste into a fresh session at the repo root.

> Build the data acquisition layer under `services/ingest/` and `services/enrich/`, following `docs/DATA.md` and `docs/TRD.md`.
>
> **Environment check first.** Verify these import: `websockets`, `httpx`, `dnspython`, `tldextract`, `rapidfuzz`, `mmh3`, `pyasn`, `playwright`. Playwright also needs `playwright install chromium` as a separate step — confirm it runs. Report back before writing anything.
>
> Then, in this order:
>
> **1. `ingest/capture.py`** — connect to `wss://certstream.calidog.io/`, write raw messages to a JSONL file for N minutes. **Run it for 30 minutes immediately** and confirm the file has content. This is our replay source and our demo insurance — it comes before everything else.
>
> **2. `ingest/stream.py`** — the live consumer. Auto-reconnect with exponential backoff, heartbeat to Redis every 5 s, expose connection state, and support replay mode reading from the capture file at configurable speed. Push extracted names to the Redis stream `certs:raw`.
>
> **3. `data/allowlist.txt`** — download Tranco, take the top 100k.
>
> **4. `data/brands.yaml`** — ~40 Indian brands per §4 above, with tokens, legit domains and sector.
>
> **5. `ingest/triage.py`** — the scoring function in `docs/TRD.md` §2. **Allowlist is checked first and short-circuits.** Profile it: it must run in under 5 ms per name. If it does not, tell me the bottleneck before optimising.
>
> **6. `enrich/enrichers.py`** — DNS, RDAP (prefer over WHOIS), ASN via pyasn, TLS chain. Each enricher fails independently; a failure marks that field unknown and sets `partial`, it does not fail the whole record.
>
> **7. `enrich/fingerprint.py`** — `dom_structure_hash`, `favicon_hash`, `js_bundle_hashes`. **Write the stability test for `dom_structure_hash` at the same time:** take one HTML page, change every string, colour, and image URL, and assert the hash does not move. This function is the strongest edge in the campaign graph — if it is unstable, nothing clusters.
>
> **8. `enrich/confirm.py`** — Playwright fetch with `httpx` fallback. Apply the confirmation rules in `docs/TRD.md` §3. **Confirmed requires at least two strong signals.** Store the reasons for every verdict. Timeouts leave the domain as `candidate`, never `dismissed`.
>
> **Rules:**
> - Never send any request to an abuse channel, registrar, or host. Fetch and observe only.
> - Never submit or interact with a form on a scanned page.
> - Respect a per-host rate limit and a 15 s hard timeout.
> - Never mark a domain confirmed without stored evidence.
> - If a source is unreachable, report it — do not substitute a different one without telling me.
>
> Start with the environment check and the 30-minute capture, and report before step 2.

---

## 8. Attribution

Free does not mean unattributed. Keep `data/MANIFEST.md` current.

- Certificate Transparency — RFC 6962, logs operated by Google, Cloudflare, Let's Encrypt, DigiCert
- certstream — Cali Dog Security
- Tranco — Tranco research list, KU Leuven
- OpenPhish · PhishTank · URLhaus (abuse.ch)
- RDAP — ICANN / IANA
- Routeviews via pyasn — University of Oregon
- Team Cymru IP-to-ASN mapping
