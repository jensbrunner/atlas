from __future__ import annotations

import random
import time
from pathlib import Path

import pytest

from atlas.agents.loop import run_tool_loop
from atlas.agents.types import AgentError, AgentReply, AgentRequest, ToolCall
from atlas.state.schemas import CampaignSeed
from atlas.state.store import CampaignStore
from atlas.tools.context import ToolContext
from atlas.tools.registry import build_default_registry
from tests.support import seed_payload


class SlowToolProvider:
    def complete(self, request: AgentRequest) -> AgentReply:
        time.sleep(0.02)
        return AgentReply(tool_calls=[ToolCall(id="call", name="unknown_tool")])


def test_tool_loop_stops_at_its_deadline(tmp_path: Path) -> None:
    store = CampaignStore(tmp_path / "campaigns")
    state = store.create(CampaignSeed.model_validate(seed_payload()), narrator_model="fake")
    ctx = ToolContext(state=state, rng=random.Random(1))

    with pytest.raises(AgentError, match="deadline"):
        run_tool_loop(
            SlowToolProvider(),  # type: ignore[arg-type]
            build_default_registry(),
            AgentRequest(model="test", instructions="test", messages=[]),
            ctx,
            max_iterations=5,
            deadline_seconds=0.01,
        )


def test_tool_loop_stops_at_max_iterations(tmp_path: Path) -> None:
    class EndlessProvider:
        def complete(self, request: AgentRequest) -> AgentReply:
            return AgentReply(tool_calls=[ToolCall(id="call", name="unknown_tool")])

    store = CampaignStore(tmp_path / "campaigns")
    state = store.create(CampaignSeed.model_validate(seed_payload()), narrator_model="fake")
    ctx = ToolContext(state=state, rng=random.Random(1))

    with pytest.raises(AgentError, match="exceeded"):
        run_tool_loop(
            EndlessProvider(),  # type: ignore[arg-type]
            build_default_registry(),
            AgentRequest(model="test", instructions="test", messages=[]),
            ctx,
            max_iterations=3,
        )


def test_identical_tool_effects_apply_once_per_turn(tmp_path: Path) -> None:
    class RepeatingProvider:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, request: AgentRequest) -> AgentReply:
            self.calls += 1
            if self.calls <= 2:
                return AgentReply(
                    tool_calls=[
                        ToolCall(
                            id=f"call_{self.calls}",
                            name="patch_inventory",
                            arguments={
                                "operation": "remove",
                                "name": "Rations",
                                "quantity": 1,
                            },
                        )
                    ]
                )
            return AgentReply(text="One ration is used.")

    store = CampaignStore(tmp_path / "campaigns")
    state = store.create(CampaignSeed.model_validate(seed_payload()), narrator_model="fake")
    ctx = ToolContext(state=state, rng=random.Random(1))

    reply = run_tool_loop(
        RepeatingProvider(),  # type: ignore[arg-type]
        build_default_registry(),
        AgentRequest(model="test", instructions="test", messages=[]),
        ctx,
        max_iterations=5,
    )

    assert reply.text == "One ration is used."
    assert state.character.inventory["rations"].quantity == 2
    assert len(ctx.changes) == 1


def test_clock_reason_wording_does_not_bypass_deduplication(tmp_path: Path) -> None:
    class RewordingProvider:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, request: AgentRequest) -> AgentReply:
            self.calls += 1
            if self.calls <= 2:
                return AgentReply(
                    tool_calls=[
                        ToolCall(
                            id=f"call_{self.calls}",
                            name="patch_clock",
                            arguments={
                                "clock": "storm_arrival",
                                "delta": 1,
                                "reason": f"wording {self.calls}",
                            },
                        )
                    ]
                )
            return AgentReply(text="The storm grows closer.")

    store = CampaignStore(tmp_path / "campaigns")
    state = store.create(CampaignSeed.model_validate(seed_payload()), narrator_model="fake")
    ctx = ToolContext(state=state, rng=random.Random(1))

    run_tool_loop(
        RewordingProvider(),  # type: ignore[arg-type]
        build_default_registry(),
        AgentRequest(model="test", instructions="test", messages=[]),
        ctx,
        max_iterations=5,
    )

    assert state.world.clocks["storm_arrival"].filled == 1
