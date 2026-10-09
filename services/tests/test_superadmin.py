"""Super admin (spec 2026-10-09 §3–§4): one platform operator signs in with a password and creates organisations by
category. The session reads no organisation data; the public list shows read-only keys only; guessing is throttled
before any password check."""
import dataclasses
from datetime import datetime, timezone

import nacl.exceptions
import nacl.pwhash
import pytest
import sqlalchemy as sa

from services.api import auth, seal
from services.api.routes import accounts

pytestmark = pytest.mark.db
EMAIL, PASSWORD = "super@example.test", "correct horse battery"
NO_KEY = {auth.HEADER: ""}


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    """Keys are sealed (so the panel and the public list can show them again) only with KEY_SEAL_SECRET set."""
    monkeypatch.setattr(seal, "SETTINGS", dataclasses.replace(seal.SETTINGS, key_seal_secret="11" * 32))


@pytest.fixture
def superadmin(db):
    h = nacl.pwhash.argon2id.str(PASSWORD.encode(), opslimit=nacl.pwhash.argon2id.OPSLIMIT_MIN,
                                 memlimit=nacl.pwhash.argon2id.MEMLIMIT_MIN).decode()
    db.execute(sa.text("insert into super_admins (email, password_hash) values (:e, :h)"), {"e": EMAIL, "h": h})


def login(api, email=EMAIL, password=PASSWORD, ip="198.51.100.7"):
    return api.post("/auth/superadmin/login", json={"email": email, "password": password},
                    headers={**NO_KEY, "CF-Connecting-IP": ip})


def session(api):
    r = login(api)
    assert r.status_code == 200, r.text
    return {auth.HEADER: r.json()["token"]}


def test_seal_round_trip_and_a_wrong_secret_fails_closed(monkeypatch):
    box = seal.seal("qcc_demo_abc")
    assert box and seal.unseal(box) == "qcc_demo_abc"
    monkeypatch.setattr(seal, "SETTINGS", dataclasses.replace(seal.SETTINGS, key_seal_secret="22" * 32))
    with pytest.raises(nacl.exceptions.CryptoError):
        seal.unseal(box)
    monkeypatch.setattr(seal, "SETTINGS", dataclasses.replace(seal.SETTINGS, key_seal_secret=""))
    assert seal.seal("x") is None


def test_wrong_password_is_401_and_the_right_one_opens_a_twelve_hour_session(api, superadmin):
    assert login(api, password="nope").status_code == 401
    assert login(api, email="someone@else.test").status_code == 401
    r = login(api)
    assert r.status_code == 200
    body = r.json()
    assert body["token"].startswith("qcc_superadmin_")
    hours = (datetime.fromisoformat(body["expires_at"]) - datetime.now(timezone.utc)).total_seconds() / 3600
    assert 11.9 < hours <= 12


def test_guessing_is_throttled_per_client_and_overall_before_any_password_check(api, superadmin, monkeypatch):
    checks = []
    real = accounts.verify_password
    monkeypatch.setattr(accounts, "verify_password", lambda h, p: checks.append(1) or real(h, p))
    for _ in range(5):
        assert login(api, password="guess", ip="203.0.113.1").status_code == 401
    r = login(api, password="guess", ip="203.0.113.1")
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert len(checks) == 5  # the sixth guess never reached argon2
    assert login(api, ip="203.0.113.1").status_code == 429  # even the right password waits
    for i in range(25):  # 30 failures overall, spread over many clients
        login(api, password="guess", ip=f"203.0.113.{100 + i}")
    assert login(api, password="guess", ip="192.0.2.50").status_code == 429


def test_a_session_runs_the_panel_and_reads_no_organisation_data(api, superadmin):
    h = session(api)
    r = api.get("/superadmin/orgs", headers=h)
    assert r.status_code == 200
    cats = {o["slug"]: o["category"] for o in r.json()}
    assert cats["org1"] == "banking" and cats["org2"] == "banking"
    assert api.get("/campaigns", headers=h).status_code == 404
    assert api.get("/admin/signals", headers=h).status_code == 404


def test_other_keys_cannot_reach_the_panel(api):
    for who in ("org1", "org2", "demo1", "admin"):
        assert api.get("/superadmin/orgs", headers=api.as_(who)).status_code == 404, who


def test_create_an_organisation_by_category(api, superadmin, seeded):
    h = session(api)
    r = api.post("/superadmin/orgs", json={"name": "ShopSafe SOC", "category": "ecommerce"}, headers=h)
    assert r.status_code == 201, r.text
    org = r.json()
    assert org["slug"] == "shopsafe-soc" and org["category"] == "ecommerce"
    assert org["org_key"].startswith("qcc_org_") and org["demo_key"].startswith("qcc_demo_")
    own = {auth.HEADER: org["org_key"]}
    assert api.get("/campaigns", headers=own).json()["items"] == []
    assert api.get(f"/campaigns/{seeded}", headers=own).status_code == 404  # Bank One's campaign does not exist for it
    assert api.get("/campaigns", headers={auth.HEADER: org["demo_key"]}).status_code == 200
    assert api.post("/superadmin/orgs", json={"name": "ShopSafe SOC", "category": "ecommerce"}, headers=h).status_code == 409
    assert api.post("/superadmin/orgs", json={"name": "Movies Inc", "category": "cinema"}, headers=h).status_code == 422
    keys = api.get("/superadmin/orgs/shopsafe-soc/keys", headers=h).json()
    assert keys == {"org_key": org["org_key"], "demo_key": org["demo_key"]}


def test_the_public_list_shows_read_only_keys_only(api, superadmin):
    h = session(api)
    made = api.post("/superadmin/orgs", json={"name": "ShopSafe SOC", "category": "ecommerce"}, headers=h).json()
    r = api.get("/orgs/public", headers=NO_KEY)
    assert r.status_code == 200
    by = {o["slug"]: o for o in r.json()}
    assert by["shopsafe-soc"] == {"slug": "shopsafe-soc", "name": "ShopSafe SOC", "category": "ecommerce",
                                  "demo_key": made["demo_key"]}
    assert by["org1"]["demo_key"] == api.keys["demo1"]
    for o in r.json():
        assert o["demo_key"] is None or o["demo_key"].startswith("qcc_demo_")


def test_rotate_and_deactivate(api, superadmin):
    h = session(api)
    org = api.post("/superadmin/orgs", json={"name": "Telco Watch", "category": "telecom"}, headers=h).json()
    new = api.post("/superadmin/orgs/telco-watch/rotate", json={"kind": "org"}, headers=h).json()["key"]
    auth.clear_cache()
    assert api.get("/campaigns", headers={auth.HEADER: org["org_key"]}).status_code == 401
    assert api.get("/campaigns", headers={auth.HEADER: new}).status_code == 200
    assert api.post("/superadmin/orgs/telco-watch/deactivate", headers=h).status_code == 200
    auth.clear_cache()
    assert api.get("/campaigns", headers={auth.HEADER: new}).status_code == 401
    assert "telco-watch" not in {o["slug"] for o in api.get("/orgs/public", headers=NO_KEY).json()}
    assert api.post("/superadmin/orgs/org1/deactivate", headers=h).status_code == 409


def test_logout_revokes_the_session_and_a_session_expires(api, superadmin, db):
    h = session(api)
    assert api.post("/auth/logout", headers=h).status_code == 204
    auth.clear_cache()
    assert api.get("/superadmin/orgs", headers=h).status_code == 401
    h2 = session(api)
    db.execute(sa.text("update api_keys set expires_at = now() - interval '1 minute' where kind = 'superadmin'"))
    auth.clear_cache()
    assert api.get("/superadmin/orgs", headers=h2).status_code == 401
    assert api.post("/auth/logout", headers=api.as_("org1")).status_code == 404  # only sessions can log out
    assert api.get("/campaigns", headers=api.as_("org1")).status_code == 200


def test_set_and_backfill_from_env(api, db):
    """`scripts.superadmin set` stores only an argon2id hash; `backfill` seals keys that already exist (created
    before sealing) only when the token matches its stored hash, and gives an organisation without one a demo key."""
    from scripts import superadmin as script
    script.set_superadmin(db, "Owner@Example.test", "s3cret-pass")
    stored = db.execute(sa.text("select password_hash from super_admins where email = 'owner@example.test'")).scalar()
    assert stored.startswith("$argon2id$") and "s3cret" not in stored
    assert login(api, email="owner@example.test", password="s3cret-pass").status_code == 200

    db.execute(sa.text("update api_keys set token_sealed = null"))  # as if created before KEY_SEAL_SECRET existed
    assert script.backfill(db, [api.keys["demo1"], "qcc_demo_not-a-real-key"]) == 1
    made = script.ensure_demo_key(db, "org2")
    assert made.startswith("qcc_demo_") and script.ensure_demo_key(db, "org2") is None  # once
    by = {o["slug"]: o["demo_key"] for o in api.get("/orgs/public", headers=NO_KEY).json()}
    assert by["org1"] == api.keys["demo1"] and by["org2"] == made


class NoChain:
    def available(self):
        return False


def provision_now(db, tmp_path):
    """Run provisioning in the test's own transaction (the real one runs in a background thread on its own
    connection, never available to tests)."""
    import nacl.signing
    from services.api import platform
    key = nacl.signing.SigningKey.generate().encode().hex()
    return lambda slug: platform.provision(db, NoChain(), slug, evidence_dir=tmp_path, signing_key_hex=key)


def test_a_new_organisation_gets_its_own_seeded_campaign_queued_for_the_ledger(api, superadmin, db, tmp_path):
    from services.api import deps, main
    from services.api.routes import superadmin as routes
    main.app.dependency_overrides[routes.get_provisioner] = lambda: provision_now(db, tmp_path)
    main.app.dependency_overrides[deps.get_ledger] = lambda: NoChain()
    h = session(api)
    org = api.post("/superadmin/orgs", json={"name": "ShopSafe SOC", "category": "ecommerce"}, headers=h).json()
    camps = api.get("/campaigns", headers={auth.HEADER: org["org_key"]}).json()["items"]
    assert len(camps) == 1 and 50 <= camps[0]["domain_count"] <= 70
    assert "Amazon India" in camps[0]["brands"]  # the sector's first brand, by default
    queued = db.execute(sa.text("""select count(*) from anchor_queue q join organisations o on o.id = q.org_id
                                   where o.slug = 'shopsafe-soc' and q.kind = 'campaign'""")).scalar()
    assert queued == 1
    listed = {o["slug"]: o for o in api.get("/superadmin/orgs", headers=h).json()}
    assert listed["shopsafe-soc"]["campaigns"] == 1 and listed["shopsafe-soc"]["chain"] == "pending"


def test_category_other_needs_a_brand_to_imitate(api, superadmin):
    h = session(api)
    assert api.post("/superadmin/orgs", json={"name": "Misc SOC", "category": "other"}, headers=h).status_code == 422
    assert api.post("/superadmin/orgs", json={"name": "Misc SOC", "category": "other", "demo_brand": "Nope"},
                    headers=h).status_code == 422
    r = api.post("/superadmin/orgs", json={"name": "Misc SOC", "category": "other", "demo_brand": "Swiggy"}, headers=h)
    assert r.status_code == 201
