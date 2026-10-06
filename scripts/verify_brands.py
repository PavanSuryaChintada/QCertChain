"""DNS-verify every legit domain in data/brands.yaml (NS or A record must exist). Exit 1 on any miss."""
import sys

import dns.resolver
import yaml

from services.config import ROOT, SETTINGS

res = dns.resolver.Resolver()
res.nameservers = ["1.1.1.1", "8.8.8.8"]
res.lifetime = 8


def exists(d: str) -> bool:
    for rtype in ("NS", "A", "SOA"):
        try:
            res.resolve(d, rtype)
            return True
        except Exception:
            continue
    return False


brands = yaml.safe_load(open(ROOT / SETTINGS.brands_file, encoding="utf-8"))
missing = [(b["name"], d) for b in brands for d in b["legit_domains"] if not exists(d)]
print(f"{len(brands)} brands, {sum(len(b['legit_domains']) for b in brands)} legit domains, missing: {missing}")
sys.exit(1 if missing else 0)
