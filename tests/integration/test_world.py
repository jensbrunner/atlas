from __future__ import annotations

from pathlib import Path

from atlas.agents.campaign import CampaignRequest
from atlas.agents.types import AgentReply
from tests.support import fake_provider, make_service, tool


def test_world_turn_advances_clock_and_is_not_player_narration(tmp_path: Path) -> None:
    provider = fake_provider()
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    provider.replies.extend(
        [
            AgentReply(
                tool_calls=[
                    tool("patch_clock", "c1", clock="storm_arrival", delta=2, reason="wind rising")
                ]
            ),
            AgentReply(text="The storm front moves closer; the council notices."),
        ]
    )

    result = service.world_turn(state.meta.id, "a day passes")

    clocks = {clock["id"]: clock for clock in result["player"]["world"]["clocks"]}
    assert clocks["storm_arrival"]["filled"] == 2
    assert "The storm front moves closer" not in str(result["player"])
    assert any(path.name.endswith("-world.md") for path in state.root.joinpath("turns").iterdir())

    gm = service.gm(state.meta.id)
    assert any(turn["kind"] == "world" for turn in gm["gm"]["turns"])


def test_world_turn_loads_after_the_player_turn_with_the_same_number(tmp_path: Path) -> None:
    provider = fake_provider()
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    service.play_turn(state.meta.id, "wait")

    provider.replies.extend(
        [
            AgentReply(tool_calls=[tool("advance_time", "c1", minutes=60)]),
            AgentReply(text="An hour passes offscreen."),
        ]
    )
    service.world_turn(state.meta.id, "night falls")

    reloaded = service.get(state.meta.id)
    kinds = [turn.kind for turn in reloaded.turns if turn.turn == 1]
    assert kinds == ["player", "world"]
    world_turn = next(turn for turn in reloaded.turns if turn.kind == "world")
    assert world_turn.world_time_before == 0
    assert world_turn.world_time_after == 60


def test_auditor_returns_configured_findings(tmp_path: Path) -> None:
    provider = fake_provider(
        audit_findings=[
            {
                "severity": "high",
                "summary": "Mara acts on a fact she does not know.",
                "evidence": "Turn 1 has Mara quoting the hidden ledger.",
            }
        ]
    )
    service = make_service(tmp_path, provider=provider)
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))

    report = service.audit(state.meta.id)
    assert report["campaign_id"] == state.meta.id
    assert report["findings"][0]["severity"] == "high"
    assert "ledger" in report["findings"][0]["evidence"]


def test_auditor_can_report_no_findings(tmp_path: Path) -> None:
    service = make_service(tmp_path, provider=fake_provider(audit_findings=[]))
    state, _ = service.create_campaign(CampaignRequest(prompt="A harbor mystery."))
    assert service.audit(state.meta.id)["findings"] == []
