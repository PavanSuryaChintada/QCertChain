"""Download Tranco top-1M, keep the top 100,000 into data/allowlist.txt. Fails loudly; no substitute source."""
import io
import sys
import zipfile
from datetime import datetime, timezone

import httpx

from services.config import ROOT, SETTINGS

URL = "https://tranco-list.eu/top-1m.csv.zip"
ID_URL = "https://tranco-list.eu/top-1m-id"

try:
    r = httpx.get(URL, follow_redirects=True, timeout=120)
    r.raise_for_status()
    list_id = httpx.get(ID_URL, follow_redirects=True, timeout=30).text.strip()
except httpx.HTTPError as e:
    print(f"Tranco unreachable: {e}. No substitute used — report to owner.", file=sys.stderr)
    sys.exit(1)

with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    rows = z.read(z.namelist()[0]).decode("utf-8").splitlines()
domains = [line.split(",", 1)[1].strip().lower() for line in rows[:100_000]]
out = ROOT / SETTINGS.allowlist_file
out.write_text("\n".join(domains) + "\n", encoding="utf-8")
stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
(ROOT / "data/tranco_list_id.txt").write_text(f"{list_id}\n{stamp}\n", encoding="utf-8")
print(f"wrote {len(domains)} domains, Tranco list {list_id}, fetched {stamp}")
