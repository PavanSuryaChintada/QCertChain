"""The platform's super admin and sealed key copies (spec 2026-10-09 §3).

    PYTHONPATH=. python -m scripts.superadmin set        # upsert the super admin from SUPERADMIN_EMAIL/_PASSWORD in .env
    PYTHONPATH=. python -m scripts.superadmin backfill   # seal the keys already in .env; give org2 a read-only key
    PYTHONPATH=. python -m scripts.superadmin chain      # register every organisation's account on this chain

The password is read from .env, never from the command line (shell history). Only its argon2id hash is stored.
`backfill` seals a token only when it matches a stored, unrevoked key hash; it never creates or prints a full key.
"""
from __future__ import annotations

import sys

import nacl.pwhash
import sqlalchemy as sa

from services.api import auth, seal


def set_superadmin(c: sa.Connection, email: str, password: str) -> None:
    h = nacl.pwhash.argon2id.str(password.encode("utf-8")).decode("ascii")
    c.execute(sa.text("""insert into super_admins (email, password_hash) values (lower(:e), :h)
                         on conflict (email) do update set password_hash = excluded.password_hash"""),
              {"e": email.strip(), "h": h})


def backfill(c: sa.Connection, tokens: list[str]) -> int:
    """Seal existing org and demo keys whose plaintext we hold. Returns how many were sealed."""
    n = 0
    for t in tokens:
        if not t:
            continue
        box = seal.seal(t)
        if box is None:
            raise SystemExit("KEY_SEAL_SECRET is not set: add 32 random bytes in hex to .env (see .env.example)")
        n += c.execute(sa.text("""update api_keys set token_sealed = :s
                                  where key_hash = :h and revoked_at is null and kind in ('org', 'demo')"""),
                       {"s": box, "h": auth.hash_key(t)}).rowcount
    return n


def ensure_demo_key(c: sa.Connection, slug: str) -> str | None:
    """A sealed read-only key for an organisation that has none (org2 never had one). Returns it, or None."""
    has = c.execute(sa.text("""select 1 from api_keys k join organisations o on o.id = k.org_id
                               where o.slug = :s and k.kind = 'demo' and k.revoked_at is null
                                 and k.token_sealed is not null"""), {"s": slug}).first()
    if has:
        return None
    return auth.create_key(c, "demo", slug, label=f"{slug}: read-only, shown on the sign-in page")


def main(argv: list[str]) -> int:
    from scripts.demo import env_keys
    from services.api.db import engine
    from services.config import SETTINGS
    cmd = argv[1] if len(argv) > 1 else ""
    with engine().begin() as c:
        if cmd == "set":
            if not (SETTINGS.superadmin_email and SETTINGS.superadmin_password):
                raise SystemExit("set SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD in .env first")
            set_superadmin(c, SETTINGS.superadmin_email, SETTINGS.superadmin_password)
            print(f"super admin {SETTINGS.superadmin_email.lower()} set (argon2id hash only)")
        elif cmd == "backfill":
            keys = env_keys()
            n = backfill(c, [keys.get(k, "") for k in ("QCC_KEY_ORG1", "QCC_KEY_ORG2", "QCC_KEY_DEMO")])
            made = ensure_demo_key(c, "org2")
            print(f"sealed {n} existing key(s); org2 read-only key {'created' if made else 'already present'}")
        elif cmd == "chain":
            from services.api import platform
            from services.api.ledger_service import Ledger
            ledger = Ledger.from_settings(SETTINGS)
            if not ledger.available():
                raise SystemExit(f"the chain at {SETTINGS.chain_rpc} is not reachable")
            print(f"registered {platform.register_all(c, ledger)} organisation account(s) on {SETTINGS.chain_rpc}")
        else:
            print(__doc__)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
