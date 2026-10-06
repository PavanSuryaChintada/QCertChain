"""Apply services/api/schema.sql. Usage: python -m scripts.apply_schema [--url URL] [--write-migration]"""
import argparse
import shutil

import psycopg

from services.config import ROOT, SETTINGS

SCHEMA = ROOT / "services/api/schema.sql"
MIGRATION = ROOT / "supabase/migrations/20261006000000_init.sql"


def plain(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def apply(url: str) -> None:
    with psycopg.connect(plain(url), autocommit=True) as c:
        c.execute(SCHEMA.read_text(encoding="utf-8"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=SETTINGS.database_url)
    ap.add_argument("--write-migration", action="store_true")
    a = ap.parse_args()
    if a.write_migration:
        MIGRATION.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SCHEMA, MIGRATION)
    apply(a.url)
    print("schema applied")
