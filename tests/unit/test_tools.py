from __future__ import annotations

import random
from pathlib import Path

from atlas.state.schemas import CampaignSeed, CampaignState
from atlas.state.store import CampaignStore
from atlas.tools.context import ToolContext
from atlas.tools.registry import build_default_registry
from tests.support import seed_payload


def _state(tmp_path: Path) -> CampaignState:
    store = CampaignStore(tmp_path / "campaigns")
    seed = CampaignSeed.model_validate(seed_payload())
    return store.create(seed, narrator_model="fake")


def _context(state: CampaignState) -> ToolContext:
    return ToolContext(state=state, rng=random.Random(1))


def test_inventory_add_remove_and_bounds(tmp_path: Path) -> None:
    state = _state(tmp_path)
    registry = build_default_registry()
    ctx = _context(state)

    added = registry.execute(
        ctx, "patch_inventory", {"operation": "add", "name": "Lantern oil", "quantity": 2}
    )
    assert "Added 2 Lantern oil" in added
    assert state.character.inventory["lantern_oil"].quantity == 2

    removed = registry.execute(
        ctx, "patch_inventory", {"operation": "remove", "name": "Lantern oil", "quantity": 2}
    )
    assert "0 remain" in removed
    assert "lantern_oil" not in state.character.inventory

    error = registry.execute(
        ctx, "patch_inventory", {"operation": "remove", "name": "Rope", "quantity": 5}
    )
    assert error.startswith("ERROR:")
    assert state.character.inventory["rope"].quantity == 1


def test_character_patch_clamps_bounds(tmp_path: Path) -> None:
    state = _state(tmp_path)
    registry = build_default_registry()
    ctx = _context(state)

    registry.execute(ctx, "patch_character", {"health_delta": 50})
    assert state.character.health.current == state.character.health.max

    registry.execute(ctx, "patch_character", {"health_delta": -99})
    assert state.character.health.current == 0

    error = registry.execute(ctx, "patch_character", {"supplies_delta": -99})
    assert error.startswith("ERROR:")


def test_clock_advance_is_bounded(tmp_path: Path) -> None:
    state = _state(tmp_path)
    registry = build_default_registry()
    ctx = _context(state)

    clock = state.world.clocks["storm_arrival"]
    registry.execute(ctx, "patch_clock", {"clock": "storm_arrival", "delta": 99})
    assert clock.filled == clock.segments

    registry.execute(ctx, "patch_clock", {"clock": "storm_arrival", "delta": -99})
    assert clock.filled == 0


def test_advance_time_is_once_per_turn(tmp_path: Path) -> None:
    state = _state(tmp_path)
    registry = build_default_registry()
    ctx = _context(state)
    before = state.meta.world_time_minutes

    first = registry.execute(ctx, "advance_time", {"minutes": 10})
    second = registry.execute(ctx, "advance_time", {"minutes": 20})

    assert "Advanced 10 minutes" in first
    assert second.startswith("ERROR:")
    assert state.meta.world_time_minutes == before + 10


def test_unknown_tool_and_bad_arguments_return_errors(tmp_path: Path) -> None:
    state = _state(tmp_path)
    registry = build_default_registry()
    ctx = _context(state)

    assert registry.execute(ctx, "teleport", {}).startswith("ERROR:")
    assert registry.execute(ctx, "advance_time", {"minutes": "later"}).startswith("ERROR:")


def test_record_and_reveal_fact(tmp_path: Path) -> None:
    state = _state(tmp_path)
    registry = build_default_registry()
    ctx = _context(state)

    result = registry.execute(
        ctx,
        "record_fact",
        {"text": "The harbourmaster burned the manifest.", "visibility": "gm"},
    )
    assert "Recorded fact" in result
    fact_id = next(key for key, fact in state.world.facts.items() if "harbourmaster" in fact.text)
    assert state.world.facts[fact_id].visibility == "gm"

    registry.execute(ctx, "reveal_fact", {"fact": fact_id})
    assert state.world.facts[fact_id].visibility == "player"


def test_set_scene_reveals_a_hidden_location(tmp_path: Path) -> None:
    state = _state(tmp_path)
    registry = build_default_registry()
    ctx = _context(state)
    assert state.world.locations["council_hall"].player_known is False

    result = registry.execute(ctx, "set_scene", {"location": "council_hall"})

    assert state.world.current_location == "council_hall"
    assert state.world.locations["council_hall"].player_known is True
    assert "discovered" in result


def test_create_location_npc_and_discovery(tmp_path: Path) -> None:
    state = _state(tmp_path)
    registry = build_default_registry()
    ctx = _context(state)

    created = registry.execute(
        ctx,
        "create_location",
        {
            "id": "old_tallowhouse",
            "name": "The Old Tallowhouse",
            "description": "A boarded warehouse that still smells of rendered fat.",
            "player_known": False,
        },
    )
    assert "Created location old_tallowhouse" in created
    assert state.world.locations["old_tallowhouse"].player_known is False

    registry.execute(ctx, "set_scene", {"location": "old_tallowhouse"})
    assert state.world.locations["old_tallowhouse"].player_known is True

    registry.execute(
        ctx,
        "create_npc",
        {
            "id": "pell",
            "name": "Pell Sorn",
            "location": "old_tallowhouse",
            "description": "A captain with rain in his boots and a bruised cheek.",
            "player_known": False,
            "goals": ["Get the cargo off the books."],
            "plans": ["Move the cogs before the next tide."],
            "knows": ["fact_hidden_debt"],
            "secret": "Pell signed the false manifest under pressure.",
        },
    )
    npc = state.npcs["pell"]
    assert npc.plans == ["Move the cogs before the next tide."]
    assert npc.knows == ["fact_hidden_debt"]
    assert npc.player_known is False
    assert "false manifest" in state.npc_bodies["pell"]

    registry.execute(ctx, "update_npc", {"npc": "pell", "add_plan": "Bribe the watchman."})
    assert "Bribe the watchman." in npc.plans

    registry.execute(ctx, "reveal_npc", {"npc": "pell"})
    assert npc.player_known is True

    state.world.factions["town_council"].player_known = False
    registry.execute(ctx, "reveal_faction", {"faction": "town_council"})
    assert state.world.factions["town_council"].player_known is True
