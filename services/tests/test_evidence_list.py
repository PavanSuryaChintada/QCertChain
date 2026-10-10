"""GET /evidence lists your organisation's newest evidence bundles, so a bundle id is never something to hunt for
(owner request 2026-10-10: "we cannot find the bundle keys anywhere"). Row-level security keeps it per organisation."""
import pytest

pytestmark = pytest.mark.db


def test_your_bundles_newest_first_each_one_opens(api, seeded):
    r = api.get("/evidence", params={"limit": 10})
    assert r.status_code == 200, r.text
    items = r.json()
    assert 0 < len(items) <= 10
    assert {"bundle_id", "domain", "campaign_id", "created_at", "anchored", "partial"} <= set(items[0])
    assert [i["created_at"] for i in items] == sorted((i["created_at"] for i in items), reverse=True)
    assert all(i["domain"] for i in items)
    assert api.get(f"/evidence/{items[0]['bundle_id']}").status_code == 200


def test_another_organisation_never_sees_them(api, seeded):
    mine = {i["bundle_id"] for i in api.get("/evidence", params={"limit": 50}).json()}
    theirs = {i["bundle_id"] for i in api.get("/evidence", params={"limit": 50}, headers=api.as_("org2")).json()}
    assert mine and not (mine & theirs)


def test_the_list_is_capped(api):
    assert api.get("/evidence", params={"limit": 500}).status_code == 422
