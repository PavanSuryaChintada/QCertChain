"""S3: the false-positive gate for the S1/S2 credential-exfiltration signals. Run it BEFORE either signal is enabled.

    PYTHONPATH=. python -m scripts.exfil_fp_gate [--pages data/legit_login_pages.txt] [--out reports/exfil_fp_gate.json]

1. Real legitimate login pages (data/legit_login_pages.txt), rendered by the pipeline's own Playwright fetch (same
   SSRF guard, never typed into or submitted). Stricter than live: each page's only "own" site is its eTLD+1, no
   brand allowlist, so a legitimate post to a sister domain or an SSO provider is COUNTED as a false positive.
2. The 45 labelled confirmation pages from scripts/evaluate.py (10 known-kit, 10 unknown-kit phishing, 25 legit).

Every false positive is listed individually with its matched text and source. Rule (owner, S3): a single false
positive on a legitimate page means that signal ships as MODERATE, not strong.

Run 1 (2026-10-07 23:05 IST): S1 0 FP, S2 6 FP (5 were POSTs fired during page load, 1 was the non-URL
"https://www."). Run 2 measures S2 after the one approved refinement: load-time requests dropped, real hostnames
only. The gate set is not tuned further: changing S2 again and re-running would turn the gate into a training set.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from services.config import ROOT, SETTINGS
from services.enrich.exfil import credential_input, exfil_endpoints, foreign_post_endpoints
from services.enrich.fetch import FetchedPage, fetch_playwright

CONCURRENCY = 4


def page_scripts(p: FetchedPage) -> list[tuple[str, str]]:
    return [(u, b.decode("utf-8", "replace")) for u, b in p.bundles] or \
        [(f"script#{i}", b.decode("utf-8", "replace")) for i, b in enumerate(p.scripts)]


def signals(p: FetchedPage, legit_sites: set[str]) -> dict:
    sc = page_scripts(p)
    return {"credential_input": credential_input(p.html),
            "S1": [h.__dict__ for h in exfil_endpoints(p.html, sc)],
            "S2": [h.__dict__ for h in foreign_post_endpoints(p.html, sc, p.final_url, legit_sites)]}


async def legit_rows(urls: list[str]) -> list[dict]:
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(url: str) -> dict:
        async with sem:
            host = urlsplit(url).hostname or ""
            try:
                p = await fetch_playwright(host, timeout_s=30, user_agent=SETTINGS.user_agent, start_url=url)
            except Exception as e:  # a crashed render is a skipped row, recorded
                return {"url": url, "reachable": False, "why": f"{type(e).__name__}: {e}"[:200]}
            if not isinstance(p, FetchedPage):
                return {"url": url, "reachable": False, "why": p.reason[:200]}
            return {"url": url, "final_url": p.final_url, "status": p.status, "reachable": True,
                    "bundles": len(p.bundles), "load_requests": len(p.requests), **signals(p, set())}
    return await asyncio.gather(*(one(u) for u in urls))


def labelled_rows() -> list[dict]:
    from scripts.evaluate import _pages
    out = []
    for name, (truth, html) in _pages().items():
        p = FetchedPage(f"https://{name}.example/", f"https://{name}.example/", 200, html, {}, [], None, None, [])
        out.append({"page": name, "truth": truth, **signals(p, {"icicibank.com"})})
    return out


def summarise(legit: list[dict], labelled: list[dict]) -> dict:
    tested = [r for r in legit if r.get("reachable") and r.get("credential_input")]
    lab_legit = [r for r in labelled if r["truth"] == "legit"]
    lab_phish = [r for r in labelled if r["truth"] == "phishing"]
    out = {}
    for sig in ("S1", "S2"):
        fps = [{"url": r["url"], "hits": r[sig]} for r in tested if r[sig]] + \
              [{"page": r["page"], "hits": r[sig]} for r in lab_legit if r[sig]]
        tp = sum(bool(r[sig]) for r in lab_phish)
        out[sig] = {"false_positives": len(fps), "false_positive_detail": fps,
                    "legit_pages_tested": len(tested) + len(lab_legit),
                    "fires_on_labelled_phishing": f"{tp}/{len(lab_phish)}",
                    "precision_on_labelled": round(tp / (tp + len(fps)), 4) if tp + len(fps) else None,
                    "ships_as": "strong" if not fps else "MODERATE (false positive on a legitimate page)"}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pages", default=str(ROOT / "data/legit_login_pages.txt"))
    ap.add_argument("--out", default=str(ROOT / "reports/exfil_fp_gate.json"))
    a = ap.parse_args()
    urls = [ln.strip() for ln in Path(a.pages).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]
    legit = asyncio.run(legit_rows(urls))
    labelled = labelled_rows()
    res = {"measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
           "dataset": {"legit_login_pages": len(urls),
                       "reachable": sum(bool(r.get("reachable")) for r in legit),
                       "reachable_with_credential_input": sum(bool(r.get("credential_input")) for r in legit),
                       "labelled_pages": len(labelled)},
           "gate": summarise(legit, labelled), "legit_rows": legit, "labelled_rows": labelled}
    Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({"dataset": res["dataset"], "gate": res["gate"]}, indent=1))


if __name__ == "__main__":
    main()
