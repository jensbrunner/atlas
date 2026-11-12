from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from atlas.agents.campaign import CampaignRequest
from atlas.state.schemas import CampaignSeed
from atlas.state.store import CampaignNotFound, CampaignStore, time_of_day
from atlas.state.validate import validate_state
from tests.support import fake_provider, make_service, seed_payload


def test_create_campaign_writes_markdown_and_opening(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    state, _ = service.create_campaign(
        CampaignRequest(prompt="A rain-soaked harbor town with a missing shipment.")
    )

    assert (state.root / "campaign.md").is_file()
    assert (state.root / "character.md").is_file()
    assert (state.root / "world.md").is_file()
    assert (state.root / "journal.md").is_file()
    assert (state.root / "turns" / "0000.md").is_file()
    assert (state.root / "npcs" / "mara.md").is_file()

    player = service.player(state.meta.id)
    assert player["campaign"]["title"].startswith("A Rain-Soaked")
    assert player["narration"]
    assert player["turns"][0]["kind"] == "opening"
    assert player["campaign"]["world_time_minutes"] == 7 * 60
    assert player["turns"][0]["world_time"] == 7 * 60


def test_player_view_hides_gm_facts_and_gm_blocks(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    player = service.player(state.meta.id)
    gm = service.gm(state.meta.id)

    rendered = str(player)
    assert "The council borrowed heavily" not in rendered
    assert "Mara has already copied" not in rendered
    assert "fact_hidden_debt" not in rendered
    assert any("storm" in fact["text"].lower() for fact in player["facts"])

    gm_rendered = str(gm["gm"])
    assert "The council borrowed heavily" in gm_rendered
    assert "Mara has already copied" in gm_rendered


def test_restart_loads_the_same_state(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    campaign_id = state.meta.id

    restarted = make_service(tmp_path)
    loaded = restarted.player(campaign_id)
    assert loaded["campaign"]["id"] == campaign_id
    assert loaded["character"]["name"] == state.character.name
    assert loaded["turns"][0]["narration"] == state.turns[0].narration

    store = CampaignStore(tmp_path / "campaigns")
    assert store.list_campaigns()[0].id == campaign_id


def test_seed_rejects_duplicate_and_colliding_ids() -> None:
    payload = seed_payload()
    payload["locations"].append({"id": "Market-Square", "name": "Duplicate"})
    with pytest.raises(ValidationError, match="location ids must be unique"):
        CampaignSeed.model_validate(payload)

    payload = seed_payload()
    payload["npcs"].append(dict(payload["npcs"][0]))
    with pytest.raises(ValidationError, match="npc ids must be unique"):
        CampaignSeed.model_validate(payload)

    payload = seed_payload()
    payload["facts"].append(dict(payload["facts"][0]))
    with pytest.raises(ValidationError, match="fact ids must be unique"):
        CampaignSeed.model_validate(payload)

    payload = seed_payload()
    payload["npcs"][0]["name"] = payload["character"]["name"]
    with pytest.raises(ValidationError, match="distinct name"):
        CampaignSeed.model_validate(payload)


def test_seed_location_references_are_slug_normalized(tmp_path: Path) -> None:
    payload = seed_payload()
    payload["current_location"] = "Market Square"
    payload["npcs"][0]["location"] = "Market Square"
    seed = CampaignSeed.model_validate(payload)

    state = CampaignStore(tmp_path / "campaigns").create(seed, narrator_model="fake")
    assert state.world.current_location == "market_square"
    assert state.npcs["mara"].location == "market_square"
    validate_state(state)


def test_seed_assigns_fact_ids_and_resolves_npc_knowledge_text() -> None:
    payload = seed_payload()
    fact = payload["facts"][0]
    fact.pop("id")
    payload["npcs"][0]["knows"] = [fact["text"]]

    seed = CampaignSeed.model_validate(payload)

    resolved_id = seed.facts[0].id
    assert resolved_id
    assert seed.npcs[0].knows == [resolved_id]


def test_seed_ignores_unknown_draft_fields() -> None:
    payload = seed_payload()
    payload["npcs"][0]["plans"] = ["Test the player before trusting them."]
    payload["npcs"][0]["voice"] = "Dry, precise, never raises her voice."
    payload["mood"] = "salt and rust"

    seed = CampaignSeed.model_validate(payload)

    assert seed.npcs[0].plans == ["Test the player before trusting them."]
    assert not hasattr(seed, "mood")


def test_player_view_hides_internal_attitudes_and_faction_goals(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    state.npcs["mara"].attitude = "secretly plans to betray the player"
    state.world.factions["town_council"].goal = "seize the harbor privately"
    service.store.save(state)

    player = service.player(state.meta.id)
    rendered = str(player)
    assert "secretly plans to betray" not in rendered
    assert "seize the harbor privately" not in rendered
    assert "attitude" not in player["npcs"][0]
    assert "goal" not in player["world"]["factions"][0]
    assert "stance" not in player["world"]["factions"][0]

    gm = service.gm(state.meta.id)
    gm_rendered = str(gm["gm"])
    assert "secretly plans to betray" in gm_rendered
    assert "seize the harbor privately" in gm_rendered


def test_second_campaign_is_told_to_avoid_existing_names(tmp_path: Path) -> None:
    provider = fake_provider()
    service = make_service(tmp_path, provider=provider)
    service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    service.create_campaign(CampaignRequest(prompt="A mountain mystery."))

    second_request = provider.structured_requests[1].user_input
    assert "Mara the Keeper" in second_request
    assert "Market Square" not in second_request


def test_store_rejects_path_traversal_and_partial_campaigns(tmp_path: Path) -> None:
    store = CampaignStore(tmp_path / "campaigns")

    with pytest.raises(CampaignNotFound):
        store.load("../outside")

    partial = tmp_path / "campaigns" / "cmp_partial"
    partial.mkdir(parents=True)
    (partial / "campaign.md").write_text("---\nid: cmp_partial\n---\n", encoding="utf-8")
    with pytest.raises(CampaignNotFound):
        store.load("cmp_partial")


def test_time_of_day_labels() -> None:
    assert time_of_day(5 * 60) == "Dawn"
    assert time_of_day(8 * 60) == "Morning"
    assert time_of_day(12 * 60) == "Afternoon"
    assert time_of_day(17 * 60) == "Evening"
    assert time_of_day(21 * 60) == "Night"
    assert time_of_day(2 * 60) == "Night"
