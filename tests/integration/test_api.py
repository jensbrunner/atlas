from __future__ import annotations

import json
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
        start_minute = campaign["world_time_minutes"]

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
        assert body["player"]["campaign"]["world_time_minutes"] == start_minute + 15
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

        status = client.get(f"/api/campaigns/{campaign_id}/world-status")
        assert status.status_code == 200
        assert status.json() == {"pending": False, "last_world_turn": None}

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


def test_api_leak_error_does_not_echo_the_secret(tmp_path: Path) -> None:
    provider = fake_provider()
    with _client(tmp_path, provider) as client:
        created = client.post("/api/campaigns", json={"prompt": "A harbor mystery."})
        campaign_id = created.json()["campaign"]["id"]
        secret = "The council borrowed heavily against harbor fees that no longer exist."
        provider.replies.append(AgentReply(text=f"The truth is: {secret}"))
        provider.replies.append(AgentReply(text=f"The truth remains: {secret}"))

        response = client.post(
            f"/api/campaigns/{campaign_id}/turns",
            json={"action": "ask about the ledger"},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "content_leak"
        assert secret not in response.text
        after = client.get(f"/api/campaigns/{campaign_id}/player").json()
        assert after["campaign"]["turn_count"] == 0


def test_usage_endpoint_reports_campaign_and_tracking(tmp_path: Path) -> None:
    provider = fake_provider()
    with _client(tmp_path, provider) as client:
        created = client.post("/api/campaigns", json={"prompt": "A harbor mystery."})
        campaign_id = created.json()["campaign"]["id"]
        client.post(f"/api/campaigns/{campaign_id}/turns", json={"action": "look"})

        response = client.get(f"/api/campaigns/{campaign_id}/usage")

        assert response.status_code == 200
        body = response.json()
        assert body["campaign"]["id"] == campaign_id
        assert body["totals"]["turns"] == 2
        assert body["turns"][-1]["kind"] == "player"
        assert body["tracking"]["provider"] == "fake"
        assert body["tracking"]["models"]["narrator"] == "gpt-6-luna"


def test_canon_endpoint_exposes_full_backing_state(tmp_path: Path) -> None:
    provider = fake_provider()
    with _client(tmp_path, provider) as client:
        created = client.post("/api/campaigns", json={"prompt": "A harbor mystery."})
        campaign_id = created.json()["campaign"]["id"]

        response = client.get(f"/api/campaigns/{campaign_id}/canon")

        assert response.status_code == 200
        body = response.json()
        assert body["counts"]["npcs"] >= 1
        assert body["counts"]["facts"] >= 1
        assert body["world"]["locations"]
        assert body["npcs"][0]["sheet"]["goals"]
        assert any(fact["visibility"] == "gm" for fact in body["world"]["facts"])
        assert body["inventory"]
        assert body["turns"][0]["kind"] == "opening"
        assert "world_time" in body["campaign"]
        assert body["campaign"]["creative_brief"].startswith("Creative brief")


def test_streaming_turn_reports_progress_and_result(tmp_path: Path) -> None:
    provider = fake_provider(
        replies=[
            AgentReply(tool_calls=[tool("advance_time", "c1", minutes=5)]),
            AgentReply(text="Five minutes pass."),
        ]
    )
    with _client(tmp_path, provider) as client:
        created = client.post("/api/campaigns", json={"prompt": "A harbor mystery."})
        campaign_id = created.json()["campaign"]["id"]

        with client.stream(
            "POST",
            f"/api/campaigns/{campaign_id}/turns/stream",
            json={"action": "wait"},
        ) as response:
            assert response.status_code == 200
            text = "".join(response.iter_text())

        events = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]
        assert any(event["type"] == "tool" and event["name"] == "advance_time" for event in events)
        done = next(event for event in events if event["type"] == "done")
        assert done["result"]["turn"] == 1
        assert done["result"]["narration"] == "Five minutes pass."
