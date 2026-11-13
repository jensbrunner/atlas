from __future__ import annotations

from pathlib import Path

from atlas.agents.campaign import CampaignRequest
from atlas.agents.types import AgentReply
from tests.support import fake_provider, make_service, tool


def test_play_turn_rolls_inventory_time_and_persists(tmp_path: Path) -> None:
    provider = fake_provider()
    replies = [
        AgentReply(
            tool_calls=[
                tool(
                    "roll",
                    "call_1",
                    label="climb the sea wall",
                    attribute="agility",
                    skill="survival",
                    difficulty=8,
                ),
                tool(
                    "patch_inventory",
                    "call_2",
                    operation="remove",
                    name="Rations",
                    quantity=1,
                ),
                tool("advance_time", "call_3", minutes=30, reason="climbing"),
            ]
        ),
        AgentReply(text="You haul yourself over the wet stone and catch your breath."),
    ]
    service = make_service(tmp_path, provider=provider)
    provider.replies.extend(replies)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))

    result = service.play_turn(state.meta.id, "climb the sea wall")

    assert result.turn == 1
    assert len(result.rolls) == 1
    assert result.rolls[0].attribute == "agility"
    assert result.rolls[0].skill == "survival"
    assert result.rolls[0].check == "Agility + survival"
    assert service.get(state.meta.id).turns[-1].narrative_lens
    assert result.player["campaign"]["world_time_minutes"] == state.meta.world_time_minutes + 30
    rations = next(item for item in result.player["inventory"] if item["name"] == "Rations")
    assert rations["quantity"] == 2

    reloaded = make_service(tmp_path).player(state.meta.id)
    assert len(reloaded["turns"]) == 2
    assert reloaded["turns"][1]["action"] == "climb the sea wall"
    assert reloaded["campaign"]["turn_count"] == 1
    assert "journal" in reloaded and "climb the sea wall" in reloaded["journal"]

    turn_file = state.root / "turns" / "0001.md"
    assert turn_file.is_file()
    assert "haul yourself" in turn_file.read_text()


def test_second_turn_uses_persisted_state(tmp_path: Path) -> None:
    provider = fake_provider()
    provider.replies.extend(
        [
            AgentReply(tool_calls=[tool("advance_time", "c1", minutes=10)]),
            AgentReply(text="Ten minutes pass."),
            AgentReply(tool_calls=[tool("advance_time", "c2", minutes=20)]),
            AgentReply(text="Twenty more minutes pass."),
        ]
    )
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))

    first = service.play_turn(state.meta.id, "wait")
    second = service.play_turn(state.meta.id, "wait again")

    assert first.player["campaign"]["world_time_minutes"] == state.meta.world_time_minutes + 10
    assert second.player["campaign"]["world_time_minutes"] == state.meta.world_time_minutes + 30
    assert second.turn == 2


def test_world_turn_runs_automatically_after_the_interval(tmp_path: Path) -> None:
    provider = fake_provider()
    provider.replies.extend(
        [
            AgentReply(text="First beat."),
            AgentReply(text="Second beat."),
            AgentReply(text="Third beat."),
            AgentReply(text="The world moves offscreen."),
        ]
    )
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))

    first = service.play_turn(state.meta.id, "one")
    second = service.play_turn(state.meta.id, "two")
    third = service.play_turn(state.meta.id, "three")

    assert first.world_turn_ran is False
    assert second.world_turn_ran is False
    assert third.world_turn_ran is True

    reloaded = service.get(state.meta.id)
    assert any(turn.kind == "world" and turn.turn == 3 for turn in reloaded.turns)
