from __future__ import annotations

from typing import Any

from atlas.state.markdown import extract_gm_block_text, strip_gm_blocks
from atlas.state.schemas import CampaignState, TurnKind
from atlas.state.store import format_world_time


def _turn_view(turn: Any) -> dict[str, Any]:
    return {
        "turn": turn.turn,
        "kind": turn.kind,
        "action": turn.action,
        "narration": turn.narration,
        "world_time": turn.world_time_after,
        "rolls": [roll.model_dump(mode="json") for roll in turn.rolls],
    }


def player_view(state: CampaignState) -> dict[str, Any]:
    world = state.world
    visible_facts = [
        {"id": fact.id, "text": fact.text, "tags": fact.tags}
        for fact in world.facts.values()
        if fact.visibility == "player" or fact.revealed_at_turn is not None
    ]
    visible_locations = [
        {"id": slug, **location.model_dump(mode="json")}
        for slug, location in world.locations.items()
        if location.player_known
    ]
    visible_factions = [
        {"id": slug, **faction.model_dump(mode="json")}
        for slug, faction in world.factions.items()
        if faction.player_known
    ]
    visible_clocks = [
        {"id": slug, **clock.model_dump(mode="json")}
        for slug, clock in world.clocks.items()
        if clock.visibility == "player"
    ]
    visible_npcs = [
        {
            "id": npc_id,
            "name": npc.name,
            "location": npc.location,
            "attitude": npc.attitude,
            "description": strip_gm_blocks(state.npc_bodies.get(npc_id, "")),
        }
        for npc_id, npc in state.npcs.items()
        if npc.player_known
    ]

    character = state.character.model_dump(mode="json")
    inventory = sorted(
        (
            {"id": slug, **item.model_dump(mode="json")}
            for slug, item in state.character.inventory.items()
        ),
        key=lambda item: item["name"].lower(),
    )

    transcript = [_turn_view(turn) for turn in state.turns if turn.kind in {"opening", "player"}]

    location = world.locations.get(world.current_location)
    return {
        "campaign": {
            "id": state.meta.id,
            "title": state.meta.title,
            "genre": state.meta.genre,
            "tone": state.meta.tone,
            "premise": state.meta.premise,
            "created_at": state.meta.created_at.isoformat(),
            "turn_count": state.meta.turn_count,
            "world_time_minutes": state.meta.world_time_minutes,
            "world_time": format_world_time(state.meta.world_time_minutes),
        },
        "character": character,
        "inventory": inventory,
        "world": {
            "situation": strip_gm_blocks(world.situation or state.world_body),
            "current_location": world.current_location,
            "location": (
                {"id": world.current_location, **location.model_dump(mode="json")}
                if location is not None
                else None
            ),
            "locations": visible_locations,
            "factions": visible_factions,
            "clocks": visible_clocks,
        },
        "npcs": visible_npcs,
        "facts": visible_facts,
        "journal": strip_gm_blocks(state.journal),
        "turns": transcript,
        "narration": transcript[-1]["narration"] if transcript else "",
    }


def gm_view(state: CampaignState) -> dict[str, Any]:
    view = player_view(state)
    view["gm"] = {
        "campaign_notes": state.campaign_body,
        "character_notes": state.character_body,
        "world_notes": state.world_body,
        "world_gm_blocks": extract_gm_block_text(state.world_body),
        "facts": [fact.model_dump(mode="json") for fact in state.world.facts.values()],
        "clocks": [
            {"id": slug, **clock.model_dump(mode="json")}
            for slug, clock in state.world.clocks.items()
        ],
        "npcs": [
            {
                "id": npc_id,
                "sheet": npc.model_dump(mode="json"),
                "notes": state.npc_bodies.get(npc_id, ""),
                "gm_blocks": extract_gm_block_text(state.npc_bodies.get(npc_id, "")),
            }
            for npc_id, npc in state.npcs.items()
        ],
        "locations": [
            {"id": slug, **location.model_dump(mode="json")}
            for slug, location in state.world.locations.items()
        ],
        "factions": [
            {"id": slug, **faction.model_dump(mode="json")}
            for slug, faction in state.world.factions.items()
        ],
        "turns": [_turn_view(turn) for turn in state.turns],
        "journal_raw": state.journal,
    }
    return view


def public_transcript(
    state: CampaignState, kinds: set[TurnKind] | None = None
) -> list[dict[str, Any]]:
    allowed = kinds or {"opening", "player"}
    return [_turn_view(turn) for turn in state.turns if turn.kind in allowed]
