"""Back up every table in the public schema as gzipped CSV, through the app's own database connection.

    PYTHONPATH=. python -m scripts.backup_tables            # -> data/backups/tables_<UTC stamp>/<table>.csv.gz

For when `pg_dump` in Docker cannot reach Supabase (seen 2026-10-09: TLS resets from Docker's network path while the
host's own connection worked). The table definitions are `services/api/schema.sql` at the commit before a
migration; restore = apply that schema, then `COPY <table> FROM` each file. data/backups/ is gitignored.
"""
from __future__ import annotations

import gzip
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from services.config import SETTINGS

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    url = SETTINGS.database_url.replace("+psycopg", "")
    out = ROOT / "data" / "backups" / f"tables_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    out.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 6):
        try:
            with psycopg.connect(url, connect_timeout=60) as conn:
                tables = [r[0] for r in conn.execute(
                    "select tablename from pg_tables where schemaname = 'public' order by tablename").fetchall()]
                total = 0
                for t in tables:
                    path = out / f"{t}.csv.gz"
                    with gzip.open(path, "wb") as f, conn.cursor().copy(f'COPY public."{t}" TO STDOUT (FORMAT csv, HEADER)') as cp:
                        for chunk in cp:
                            f.write(chunk)
                    rows = conn.execute(f'select count(*) from public."{t}"').fetchone()[0]
                    total += rows
                    print(f"{t}: {rows} rows", flush=True)
            print(f"BACKUP OK: {len(tables)} tables, {total} rows -> {out}", flush=True)
            return 0
        except Exception as e:  # noqa: BLE001 - flaky home network: retry the whole run
            print(f"attempt {attempt} failed: {type(e).__name__}: {str(e).splitlines()[0][:160]}", flush=True)
            time.sleep(20)
    print("BACKUP FAILED", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
