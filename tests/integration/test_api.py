from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from atlas.agents.types import AgentReply
from atlas.app import create_app
from atlas.config import Settings
from tests.support import fake_provider, tool


def _client(tmp_path: Path, provider: object) -> TestClient:
    settings = Settings(data_dir=tmp_path / "campaigns", provider="fake")
    app = create_app(settings, provider=provider)  # type: ignore[arg-type]
    return TestClient(app)


def test_health_config_and_campaign_roundtrip(tmp_path: Path) -> None:
    provider = fake_provider(
        replies=[
            AgentReply(
                tool_calls=[
                    tool("advance_time", "c1", minutes=15),
                    tool(
                        "patch_inventory",
                        "c2",
                        operation="add",
                        name="Lantern",
                        quantity=1,
                    ),
                ]
            ),
            AgentReply(text="A lantern is pressed into your hands and fifteen minutes vanish."),
        ]
    )
    with _client(tmp_path, provider) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["provider"] == "fake"

        config = client.get("/api/config").json()
        assert config["models"]["narrator"] == "gpt-6-luna"

        created = client.post(
            "/api/campaigns",
            json={"prompt": "A harbor town with a missing shipment."},
        )
        assert created.status_code == 201
        campaign = created.json()["campaign"]
        campaign_id = campaign["id"]
        assert campaign["turn_count"] == 0

        player = client.get(f"/api/campaigns/{campaign_id}/player")
        assert player.status_code == 200
        assert "The council borrowed heavily" not in player.text
        assert "Mara has already copied" not in player.text

        gm = client.get(f"/api/campaigns/{campaign_id}/gm")
        assert "The council borrowed heavily" in gm.text

        played = client.post(
            f"/api/campaigns/{campaign_id}/turns",
            json={"action": "ask for a lantern"},
        )
        assert played.status_code == 200
        body = played.json()
        assert body["turn"] == 1
        assert body["player"]["campaign"]["world_time_minutes"] == 15
        assert any(item["name"] == "Lantern" for item in body["player"]["inventory"])

        turns = client.get(f"/api/campaigns/{campaign_id}/turns").json()["turns"]
        assert [turn["kind"] for turn in turns] == ["opening", "player"]

        listing = client.get("/api/campaigns").json()["campaigns"]
        assert listing[0]["id"] == campaign_id

        deleted = client.delete(f"/api/campaigns/{campaign_id}")
        assert deleted.status_code == 200
        assert client.get(f"/api/campaigns/{campaign_id}/player").status_code == 404


def test_api_world_turn_and_audit(tmp_path: Path) -> None:
    provider = fake_provider(
        replies=[
            AgentReply(
                tool_calls=[
                    tool("patch_clock", "c1", clock="storm_arrival", delta=1),
                ]
            ),
            AgentReply(text="The wind picks up off the water."),
        ],
        audit_findings=[{"severity": "low", "summary": "Minor drift.", "evidence": "Turn 0."}],
    )
    with _client(tmp_path, provider) as client:
        created = client.post("/api/campaigns", json={"prompt": "A harbor mystery."})
        campaign_id = created.json()["campaign"]["id"]

        world = client.post(
            f"/api/campaigns/{campaign_id}/world-turn",
            json={"reason": "dusk"},
        )
        assert world.status_code == 200
        clocks = {item["id"]: item for item in world.json()["player"]["world"]["clocks"]}
        assert clocks["storm_arrival"]["filled"] == 1

        audit = client.post(f"/api/campaigns/{campaign_id}/audit")
        assert audit.status_code == 200
        assert audit.json()["findings"][0]["summary"] == "Minor drift."


def test_api_validation_and_not_found(tmp_path: Path) -> None:
    provider = fake_provider()
    with _client(tmp_path, provider) as client:
        assert (
            client.post("/api/campaigns/cmp_missing/turns", json={"action": "x"}).status_code == 404
        )
        assert client.post("/api/campaigns", json={"unknown": "field"}).status_code == 422
        created = client.post("/api/campaigns", json={"prompt": "A harbor mystery."})
        campaign_id = created.json()["campaign"]["id"]
        empty = client.post(f"/api/campaigns/{campaign_id}/turns", json={"action": ""})
        assert empty.status_code == 422
