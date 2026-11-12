from __future__ import annotations

from pathlib import Path

import pytest

from atlas.agents.campaign import CampaignRequest
from atlas.agents.types import AgentError, AgentReply
from atlas.errors import LeakDetected
from atlas.state.store import CampaignStore
from tests.support import FailingProvider, fake_provider, make_service, seed_payload, tool


def test_unrepaired_leak_is_rejected(tmp_path: Path) -> None:
    provider = fake_provider()
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    secret = state.world.facts["fact_hidden_debt"].text
    provider.replies.extend(
        [
            AgentReply(text=f"Here is the truth: {secret}"),
            AgentReply(text=f"The ledger still says: {secret}"),
        ]
    )

    with pytest.raises(LeakDetected) as caught:
        service.play_turn(state.meta.id, "ask about the ledger")

    assert secret not in str(caught.value)
    reloaded = service.get(state.meta.id)
    assert reloaded.meta.turn_count == 0
    assert not (reloaded.root / "turns" / "0001.md").exists()


def test_leak_is_repaired_before_commit(tmp_path: Path) -> None:
    provider = fake_provider()
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    secret = state.world.facts["fact_hidden_debt"].text
    provider.replies.extend(
        [
            AgentReply(text=f"Here is the truth: {secret}"),
            AgentReply(text="Mara studies you and decides to keep her answer to herself."),
        ]
    )

    result = service.play_turn(state.meta.id, "ask about the ledger")

    assert result.turn == 1
    assert secret not in result.narration
    assert secret not in str(result.player)
    assert service.get(state.meta.id).meta.turn_count == 1


def test_repair_can_reveal_a_fact_instead_of_removing_it(tmp_path: Path) -> None:
    provider = fake_provider()
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    secret = state.world.facts["fact_hidden_debt"].text
    provider.replies.extend(
        [
            AgentReply(text=f"Here is the truth: {secret}"),
            AgentReply(tool_calls=[tool("reveal_fact", "c1", fact="fact_hidden_debt")]),
            AgentReply(text=f"Mara lays it out plainly: {secret}"),
        ]
    )

    result = service.play_turn(state.meta.id, "ask about the ledger")

    assert secret in result.narration
    assert any(fact["id"] == "fact_hidden_debt" for fact in result.player["facts"])


def test_hidden_name_is_matched_on_word_boundaries(tmp_path: Path) -> None:
    payload = seed_payload()
    payload["npcs"][0]["player_known"] = False
    provider = fake_provider(seed=payload)
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    # "Mara" is hidden, but "marathon" is an ordinary word and must not trip.
    provider.replies.append(AgentReply(text="The marathon continues along the wet street."))

    result = service.play_turn(state.meta.id, "keep walking")
    assert result.turn == 1


def test_hidden_faction_name_in_narration_is_rejected(tmp_path: Path) -> None:
    payload = seed_payload()
    payload["factions"][0]["player_known"] = False
    provider = fake_provider(seed=payload)
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    provider.replies.append(AgentReply(text="The Town Council meets at dawn."))
    provider.replies.append(AgentReply(text="The Town Council still meets at dawn."))

    with pytest.raises(LeakDetected):
        service.play_turn(state.meta.id, "listen at the door")


def test_provider_failure_leaves_files_untouched(tmp_path: Path) -> None:
    provider = FailingProvider(campaign_seed=fake_provider().campaign_seed)
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    before = (state.root / "campaign.md").read_text()

    with pytest.raises(AgentError):
        service.play_turn(state.meta.id, "look around")

    assert (state.root / "campaign.md").read_text() == before
    assert not (state.root / "turns" / "0001.md").exists()
    assert CampaignStore(tmp_path / "campaigns").list_campaigns()[0].turn_count == 0


def test_rejected_tool_call_does_not_abort_the_turn(tmp_path: Path) -> None:
    provider = fake_provider()
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    provider.replies.extend(
        [
            AgentReply(
                tool_calls=[
                    # The character carries exactly one rope.
                    tool(
                        "patch_inventory",
                        "c1",
                        operation="remove",
                        name="Rope",
                        quantity=5,
                    )
                ]
            ),
            AgentReply(text="The rope stays where it is."),
        ]
    )

    result = service.play_turn(state.meta.id, "cut the rope")
    assert any(item["name"] == "Rations" for item in result.player["inventory"])
    rope = next(item for item in result.player["inventory"] if item["name"] == "Rope")
    assert rope["quantity"] == 1
