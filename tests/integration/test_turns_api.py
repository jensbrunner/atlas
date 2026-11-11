from __future__ import annotations

import json
import uuid

from atlas.config import Settings
from atlas.main import create_app
from atlas.persistence.orm import RollRow
from atlas.seed.broken_span import SeedResult
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

SECRET_MARKERS = (
    "caravan_guild_secret",
    "Caravan Guild Secret",
    "M0_GM_ONLY_CARAVAN_STONE_SOURCE",
    "guild knows a suitable sacred stone seam",
)


def _client(database_url: str) -> TestClient:
    app = create_app(Settings(database_url=database_url, mode="offline_test"))
    return TestClient(app)


def _post_turn(
    client: TestClient,
    campaign_id: str,
    text: str,
    *,
    client_action_id: str | None = None,
    expected_version: int | None = None,
) -> Response:
    body: dict[str, object] = {
        "client_action_id": client_action_id or str(uuid.uuid4()),
        "player_text": text,
    }
    if expected_version is not None:
        body["expected_version"] = expected_version
    return client.post(f"/api/v1/campaigns/{campaign_id}/turns", json=body)


def _assert_no_secrets(payload: object) -> None:
    text = json.dumps(payload)
    assert "seed_ref" not in text
    for marker in SECRET_MARKERS:
        assert marker not in text


def test_turn_endpoints_expose_player_safe_state(
    database_url: str, seed_result: SeedResult
) -> None:
    campaign_id = seed_result.campaign.id
    with _client(database_url) as client:
        created = _post_turn(client, campaign_id, "look around")
        assert created.status_code == 200
        turn = created.json()
        assert turn["status"] == "COMMITTED"
        assert turn["ordinal"] == 1
        assert turn["campaign_version"] == 1
        assert turn["roll"] is None
        assert "Market Square" in turn["narration"]
        assert len(turn["observations"]) == 1
        assert turn["observations"][0]["kind"] == "observation"
        _assert_no_secrets(turn)

        listed = client.get(f"/api/v1/campaigns/{campaign_id}/turns")
        assert listed.status_code == 200
        listed_body = listed.json()
        assert [item["id"] for item in listed_body["turns"]] == [turn["id"]]
        assert listed_body["next_cursor"] is None
        _assert_no_secrets(listed_body)

        fetched = client.get(f"/api/v1/campaigns/{campaign_id}/turns/{turn['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == turn["id"]

        state = client.get(f"/api/v1/campaigns/{campaign_id}/state")
        assert state.status_code == 200
        state_body = state.json()
        assert state_body["state_version"] == 1
        assert state_body["scene"]["actor"]["slug"] == "rowan"
        assert state_body["scene"]["location"]["slug"] == "town_square"
        present_slugs = {entity["slug"] for entity in state_body["scene"]["present"]}
        assert present_slugs == {"magistrate_elin", "vessa_captain"}
        assert len(state_body["recent_observations"]) == 1
        slugs = {entity["slug"] for entity in state_body["entities"]}
        assert "rowan" in slugs
        assert "caravan_guild_secret" not in slugs
        _assert_no_secrets(state_body)

        journal = client.get(f"/api/v1/campaigns/{campaign_id}/journal")
        assert journal.status_code == 200
        journal_body = journal.json()
        assert len(journal_body["entries"]) == 1
        assert journal_body["next_cursor"] is None
        _assert_no_secrets(journal_body)


def test_search_roll_is_returned_without_its_seed(
    database_url: str,
    seed_result: SeedResult,
    session_factory: sessionmaker[Session],
) -> None:
    campaign_id = seed_result.campaign.id
    with _client(database_url) as client:
        response = _post_turn(client, campaign_id, "search the square")
        assert response.status_code == 200
        turn = response.json()
        assert turn["roll"] is not None
        assert len(turn["roll"]["dice"]) == 2
        assert turn["roll"]["outcome"] in {
            "failure",
            "mixed_success",
            "success",
            "critical_success",
        }
        _assert_no_secrets(turn)

        with session_factory() as session:
            roll = session.scalars(select(RollRow).where(RollRow.turn_id == turn["id"])).one()
            raw_seed = roll.seed_ref
        assert raw_seed and raw_seed not in json.dumps(turn)

        journal = client.get(f"/api/v1/campaigns/{campaign_id}/journal")
        assert journal.status_code == 200
        entries = journal.json()["entries"]
        assert len(entries) == 1
        assert entries[0]["kind"] == "search"
        _assert_no_secrets(journal.json())


def test_duplicate_submission_returns_the_same_turn(
    database_url: str, seed_result: SeedResult
) -> None:
    campaign_id = seed_result.campaign.id
    client_id = str(uuid.uuid4())
    with _client(database_url) as client:
        first = _post_turn(client, campaign_id, "wait 10 minutes", client_action_id=client_id)
        second = _post_turn(client, campaign_id, "wait 10 minutes", client_action_id=client_id)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]

        state = client.get(f"/api/v1/campaigns/{campaign_id}/state").json()
        assert state["state_version"] == 1
        assert state["current_time"] == 10
        journal = client.get(f"/api/v1/campaigns/{campaign_id}/journal").json()
        assert len(journal["entries"]) == 1


def test_expected_version_conflict_is_409_and_creates_no_turn(
    database_url: str, seed_result: SeedResult
) -> None:
    campaign_id = seed_result.campaign.id
    with _client(database_url) as client:
        conflict = _post_turn(client, campaign_id, "look around", expected_version=7)
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "version_conflict"

        turns = client.get(f"/api/v1/campaigns/{campaign_id}/turns").json()
        assert turns["turns"] == []
        state = client.get(f"/api/v1/campaigns/{campaign_id}/state").json()
        assert state["state_version"] == 0


def test_invalid_action_is_422_and_repeat_is_409(
    database_url: str, seed_result: SeedResult
) -> None:
    campaign_id = seed_result.campaign.id
    client_id = str(uuid.uuid4())
    with _client(database_url) as client:
        rejected = _post_turn(client, campaign_id, "summon a dragon", client_action_id=client_id)
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "unparsed_intent"

        repeat = _post_turn(client, campaign_id, "summon a dragon", client_action_id=client_id)
        assert repeat.status_code == 409
        assert repeat.json()["error"]["code"] == "turn_failed"

        state = client.get(f"/api/v1/campaigns/{campaign_id}/state").json()
        assert state["state_version"] == 0
        journal = client.get(f"/api/v1/campaigns/{campaign_id}/journal").json()
        assert journal["entries"] == []
        turns = client.get(f"/api/v1/campaigns/{campaign_id}/turns").json()
        assert turns["turns"] == []


def test_missing_campaign_and_turn_return_404(database_url: str, seed_result: SeedResult) -> None:
    campaign_id = seed_result.campaign.id
    with _client(database_url) as client:
        assert (
            client.post(
                "/api/v1/campaigns/cmp_missing/turns",
                json={
                    "client_action_id": str(uuid.uuid4()),
                    "player_text": "look around",
                },
            ).status_code
            == 404
        )
        for path in ("state", "journal", "turns"):
            response = client.get(f"/api/v1/campaigns/cmp_missing/{path}")
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "not_found"

        missing_turn = client.get(f"/api/v1/campaigns/{campaign_id}/turns/trn_missing")
        assert missing_turn.status_code == 404
        assert missing_turn.json()["error"]["code"] == "not_found"


def test_rejects_malformed_turn_requests(database_url: str, seed_result: SeedResult) -> None:
    campaign_id = seed_result.campaign.id
    with _client(database_url) as client:
        bad_id = client.post(
            f"/api/v1/campaigns/{campaign_id}/turns",
            json={"client_action_id": "x" * 36, "player_text": "look around"},
        )
        assert bad_id.status_code == 422
        assert bad_id.json()["error"]["code"] == "invalid_turn_plan"

        blank = client.post(
            f"/api/v1/campaigns/{campaign_id}/turns",
            json={"client_action_id": str(uuid.uuid4()), "player_text": "   "},
        )
        assert blank.status_code == 422
