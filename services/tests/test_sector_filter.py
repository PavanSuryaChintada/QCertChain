"""The Live queue shows an organisation its own sector first (spec 2026-10-09 §5): /candidates filters by the
sector's brands, and /status names the organisation's category so the console can default to it."""
from datetime import datetime, timezone

import pytest

from services.api import repo
from services.ingest.triage import triage

pytestmark = pytest.mark.db


def candidate(db, name):
    t = triage(name)
    repo.upsert_candidate(db, name=name, etld1=t.etld1, cert_id=None, triage=t, source="certstream",
                          ct_seen_at=datetime.now(timezone.utc))


def test_candidates_filter_by_the_brands_of_a_sector(api, db):
    candidate(db, "sbi-verify-kyc.top")
    candidate(db, "amazon-login-verify.top")
    names = lambda q: {c["name"] for c in api.get(f"/candidates?status=candidate{q}").json()["items"]}  # noqa: E731
    assert names("&sector=ecommerce") == {"amazon-login-verify.top"}
    assert names("&sector=banking") == {"sbi-verify-kyc.top"}
    assert {"amazon-login-verify.top", "sbi-verify-kyc.top"} <= names("")
    assert api.get("/candidates?sector=cinema").status_code == 422


def test_status_names_the_organisations_category(api):
    assert api.get("/status").json()["org"]["category"] == "banking"
