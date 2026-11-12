from __future__ import annotations

import random
from pathlib import Path

from atlas.context import build_turn_prompt
from atlas.retrieval import select_context
from atlas.state.schemas import NPC, CampaignSeed, CampaignState, Fact
from atlas.state.store import CampaignStore
from atlas.tools.context import ToolContext
from atlas.tools.registry import build_default_registry
from tests.support import seed_payload


def _state(tmp_path: Path) -> CampaignState:
    state = CampaignStore(tmp_path / "campaigns").create(
        CampaignSeed.model_validate(seed_payload()), narrator_model="fake"
    )
    state.npcs["sable"] = NPC(
        id="sable",
        name="Sable the Herbwife",
        location="harbor",
        attitude="guarded",
        goals=["Keep the poison out of the wrong hands"],
    )
    state.npc_bodies["sable"] = "Sable keeps moonwort poison in a locked satchel."
    state.world.facts["fact_moonwort"] = Fact(
        id="fact_moonwort",
        text="The moonwort poison came from Sable's satchel.",
        visibility="gm",
        tags=["poison", "sable"],
    )
    for index in range(200):
        state.world.facts[f"fact_noise_{index}"] = Fact(
            id=f"fact_noise_{index}",
            text=f"Routine background fact {index} about rope, rain, and harbor paperwork.",
            visibility="player",
        )
    for index in range(120):
        state.npcs[f"crowd_{index}"] = NPC(
            id=f"crowd_{index}",
            name=f"Crowd Member {index}",
            location="harbor",
            attitude="busy",
        )
    return state


def test_selection_keeps_relevant_people_and_facts(tmp_path: Path) -> None:
    state = _state(tmp_path)

    selection = select_context(
        state,
        "I ask Sable about the moonwort poison in her satchel.",
        mode="narrator",
    )

    assert "mara" in selection.npcs
    assert "sable" in selection.npcs
    assert "fact_moonwort" in selection.facts
    assert "fact_noise_0" not in selection.facts
    assert len(selection.npcs) <= 6
    assert selection.totals["fact"] == 203
    assert "npc" in selection.totals


def test_named_external_npc_beats_the_present_crowd(tmp_path: Path) -> None:
    state = _state(tmp_path)
    for index in range(20):
        state.npcs[f"present_{index}"] = NPC(
            id=f"present_{index}",
            name=f"Present Citizen {index}",
            location="market_square",
            attitude="busy",
        )

    selection = select_context(
        state,
        "I ask Sable about the moonwort poison.",
        mode="narrator",
    )

    assert "sable" in selection.npcs
    assert len(selection.npcs) <= 6


def test_prompt_is_bounded_and_points_to_lookup(tmp_path: Path) -> None:
    state = _state(tmp_path)

    prompt = build_turn_prompt(
        state,
        "I ask Sable about the moonwort poison in her satchel.",
        char_budget=20_000,
    )

    assert "The moonwort poison came from Sable's satchel." in prompt
    assert "Routine background fact 0 " not in prompt
    assert "lookup_canon" in prompt
    assert "Context packet:" in prompt
    assert len(prompt) <= 20_000


def test_lookup_tool_finds_omitted_canon(tmp_path: Path) -> None:
    state = _state(tmp_path)
    registry = build_default_registry()
    ctx = ToolContext(state=state, rng=random.Random(1))

    result = registry.execute(ctx, "lookup_canon", {"query": "moonwort poison"})

    assert "Sable the Herbwife" in result
    assert "fact_moonwort" in result
    assert "Crowd Member" not in result

    missing = registry.execute(ctx, "lookup_canon", {"query": "nonexistent glasswing"})
    assert "No canon matches" in missing

    by_id = registry.execute(
        ctx,
        "lookup_canon",
        {"query": "fact_moonwort", "kind": "fact"},
    )
    assert "moonwort poison" in by_id
