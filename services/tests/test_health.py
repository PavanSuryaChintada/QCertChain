"""T17/S8: /health shows per-endpoint p95 and the API/database regions, so co-location is visible on screen."""
from services.api import health, timing


def test_database_region_is_read_from_the_supabase_pooler_host():
    url = "postgresql+psycopg://postgres.x:pw@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
    assert health.database_region(url) == "ap-southeast-1"
    assert health.database_region("postgresql+psycopg://u:p@localhost:5433/db") == "local"


def test_colocation_compares_cities_not_provider_names(monkeypatch):
    monkeypatch.setenv("API_REGION", "asia-southeast1-eqsg3a")  # Railway Singapore
    import dataclasses
    monkeypatch.setattr(health, "SETTINGS", dataclasses.replace(
        health.SETTINGS, database_url="postgresql://u:p@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"))
    monkeypatch.setattr(health, "_rtt", {"at": 0.0, "value": None})
    r = health.report(lambda: (_ for _ in ()).throw(ConnectionError("not in this test")))
    assert r["regions"]["colocated"] is True and r["regions"]["api_city"] == "Singapore"
    assert r["status"] == "degraded" and r["database_round_trip_ms"] is None  # DB down is reported, not hidden


def test_p95_per_route_template_over_the_window():
    timing.reset()
    for ms in range(1, 101):  # nearest-rank percentiles
        timing.record("GET /campaigns/{campaign_id}", float(ms), now=1000.0)
    timing.record("GET /campaigns", 5.0, now=1000.0 - 400)  # older than the 5-minute window
    s = timing.summary(now=1000.0)
    assert s == {"GET /campaigns/{campaign_id}": {"count": 100, "p50_ms": 51.0, "p95_ms": 95.0}}
    timing.reset()


def test_health_is_public_and_reports_endpoint_latency(api):
    api.get("/campaigns")
    r = api.get("/health", headers={"X-API-Key": ""})
    assert r.status_code == 200
    body = r.json()
    assert "GET /campaigns" in body["endpoints"] and {"api", "database", "colocated"} <= set(body["regions"])
