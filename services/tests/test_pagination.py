"""Keyset pagination (T13): default page 50, hard max 200, opaque cursors, no OFFSET, no unbounded SELECT."""
import pytest


@pytest.mark.db
def test_cursor_walks_every_candidate_exactly_once(api, seeded):
    seen, cursor, pages = [], None, 0
    while True:
        q = "/candidates?limit=7" + (f"&cursor={cursor}" if cursor else "")
        body = api.get(q).json()
        assert set(body) == {"items", "limit", "next_cursor"} and body["limit"] == 7
        seen += [c["id"] for c in body["items"]]
        pages += 1
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 60 and pages == 9  # 8 full pages of 7 + one of 4
    firsts = [c["first_seen"] for c in api.get("/candidates?limit=200").json()["items"]]
    assert firsts == sorted(firsts, reverse=True)


@pytest.mark.db
def test_default_page_is_50_and_max_is_200(api, seeded):
    assert len(api.get("/candidates").json()["items"]) == 50
    for path in ("/candidates", "/campaigns", "/email/analyses", "/ops/log"):
        assert api.get(f"{path}?limit=201").status_code == 422, path
        assert api.get(f"{path}?limit=200").status_code == 200, path


@pytest.mark.db
def test_a_tampered_cursor_is_422_not_500(api, seeded):
    for bad in ("not-a-cursor", "W10", "WyJ4Il0"):  # garbage, [], ["x"] (wrong arity)
        assert api.get(f"/candidates?cursor={bad}").status_code == 422


@pytest.mark.db
def test_candidate_counts_match_the_listing(api, seeded):
    c = api.get("/candidates/counts").json()
    assert c["all"] == 60 and c["confirmed"] == 60 and c["candidate"] == 0
    assert api.get("/candidates/counts", headers=api.as_("org2")).json()["all"] == 0  # seed is org1-private
