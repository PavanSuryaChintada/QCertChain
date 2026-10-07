"""Create an API key. The token is printed ONCE; only its SHA-256 is stored.

  python -m scripts.create_api_key --kind org --org org1 --label "Bank One SOC analysts"
  python -m scripts.create_api_key --kind demo --org org1 --label "evaluators (read-only)"
  python -m scripts.create_api_key --kind admin --label "platform admin"
  python -m scripts.create_api_key --revoke qcc_org_AbCd   # by prefix
"""
from __future__ import annotations

import argparse

import sqlalchemy as sa

from services.api import auth
from services.api.db import engine


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["org", "demo", "admin"])
    ap.add_argument("--org", help="org slug (org1, org2); not for admin keys")
    ap.add_argument("--label")
    ap.add_argument("--revoke", metavar="PREFIX", help="revoke the key(s) with this prefix")
    a = ap.parse_args()
    with engine().begin() as c:
        if a.revoke:
            n = c.execute(sa.text("update api_keys set revoked_at = now() where prefix = :p and revoked_at is null"),
                          {"p": a.revoke[:12]}).rowcount
            print(f"revoked {n} key(s)")
            return
        if not a.kind:
            ap.error("--kind is required")
        token = auth.create_key(c, a.kind, a.org, a.label)
    print(token)


if __name__ == "__main__":
    main()
