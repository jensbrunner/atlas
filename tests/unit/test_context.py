from __future__ import annotations

from pathlib import Path

from atlas.context import (
    build_audit_prompt,
    build_turn_prompt,
    build_world_prompt,
    character_sheet,
)
from atlas.state.schemas import CampaignSeed, CampaignState
from atlas.state.store import CampaignStore
from tests.support import seed_payload


def _state(tmp_path: Path) -> CampaignState:
    state = CampaignStore(tmp_path / "campaigns").create(
        CampaignSeed.model_validate(seed_payload()), narrator_model="fake"
    )
    state.campaign_body = "Old campaign notes. " * 2_000
    state.character_body = "A weathered roadwright with rain in her boots."
    return state


def test_turn_prompt_truncates_context_but_keeps_action_and_instructions(
    tmp_path: Path,
) -> None:
    prompt = build_turn_prompt(
        _state(tmp_path),
        "I open the ledger and read the last entry.",
        char_budget=3_000,
    )

    assert len(prompt) <= 3_000
    assert "# Player action" in prompt
    assert "I open the ledger and read the last entry." in prompt
    assert "Narrate the outcome of this action." in prompt


def test_world_and_audit_prompts_keep_their_instructions(tmp_path: Path) -> None:
    state = _state(tmp_path)

    world = build_world_prompt(state, "night falls", char_budget=3_000)
    assert len(world) <= 3_000
    assert "Update the offscreen world" in world

    audit = build_audit_prompt(state, char_budget=3_000)
    assert len(audit) <= 3_000
    assert "Find contradictions with established canon" in audit


def test_character_background_reaches_the_narrator(tmp_path: Path) -> None:
    sheet = character_sheet(_state(tmp_path))
    assert "A weathered roadwright" in sheet


def test_prompt_names_the_present_cast_and_time_phase(tmp_path: Path) -> None:
    prompt = build_turn_prompt(_state(tmp_path), "look around")
    assert "NPCs present: Mara the Keeper" in prompt
    assert "Dawn" in prompt
