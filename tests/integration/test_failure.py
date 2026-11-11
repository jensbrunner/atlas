from __future__ import annotations

from pathlib import Path

import pytest

from atlas.agents.campaign import CampaignRequest
from atlas.agents.types import AgentError, AgentReply
from atlas.errors import LeakDetected
from atlas.state.store import CampaignStore
from tests.support import FailingProvider, fake_provider, make_service, tool


def test_hidden_fact_text_in_narration_is_rejected(tmp_path: Path) -> None:
    provider = fake_provider()
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    secret = state.world.facts["fact_hidden_debt"].text
    provider.replies.append(AgentReply(text=f"Here is the truth: {secret}"))

    with pytest.raises(LeakDetected):
        service.play_turn(state.meta.id, "ask about the ledger")

    reloaded = service.get(state.meta.id)
    assert reloaded.meta.turn_count == 0
    assert not (reloaded.root / "turns" / "0001.md").exists()


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
