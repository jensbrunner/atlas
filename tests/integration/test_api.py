from __future__ import annotations

from atlas.config import Settings
from atlas.main import create_app
from atlas.persistence.migrations import upgrade_database
from fastapi.testclient import TestClient


def test_health_and_campaign_endpoints(database_url: str) -> None:
    upgrade_database(database_url)
    app = create_app(Settings(database_url=database_url, mode="offline_test"))

    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        body = health.json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"
        assert body["mode"] == "offline_test"
        assert body["schema_version"]

        created = client.post("/api/v1/campaigns", json={})
        assert created.status_code == 201
        campaign = created.json()
        assert campaign["title"] == "The Broken Span"
        assert campaign["state_version"] == 0
        campaign_id = campaign["id"]
        assert campaign_id.startswith("cmp_")

        listed = client.get("/api/v1/campaigns")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["campaigns"]] == [campaign_id]

        fetched = client.get(f"/api/v1/campaigns/{campaign_id}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == campaign_id

        missing = client.get("/api/v1/campaigns/cmp_missing")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"


def test_health_reports_missing_schema(database_url: str) -> None:
    app = create_app(Settings(database_url=database_url, mode="offline_test"))
    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.status_code == 503
        assert response.json()["status"] == "degraded"
