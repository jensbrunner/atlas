from __future__ import annotations

from pathlib import Path

from atlas.agents.campaign import CampaignRequest
from atlas.state.store import CampaignStore
from tests.support import make_service


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
