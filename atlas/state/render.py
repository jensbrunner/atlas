from __future__ import annotations

from typing import Any

from atlas.pricing import price_for
from atlas.state.markdown import extract_gm_block_text, strip_gm_blocks
from atlas.state.schemas import CampaignState, TurnKind
from atlas.state.store import format_world_time, time_of_day


def _turn_view(turn: Any) -> dict[str, Any]:
    return {
        "turn": turn.turn,
        "kind": turn.kind,
        "action": turn.action,
        "narration": turn.narration,
        "world_time": turn.world_time_after,
        "rolls": [roll.model_dump(mode="json") for roll in turn.rolls],
    }


def usage_view(
    state: CampaignState,
    *,
    fallback_input: float = 0.0,
    fallback_output: float = 0.0,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    input_tokens = output_tokens = 0
    estimated_usd = 0.0
    models: set[str] = set()
    model_prices: dict[str, dict[str, Any]] = {}

    for turn in state.turns:
        usage = turn.usage
        total = usage.input_tokens + usage.output_tokens
        input_tokens += usage.input_tokens
        output_tokens += usage.output_tokens
        if turn.model:
            models.add(turn.model)

        quote = price_for(
            turn.model,
            fallback_input=fallback_input,
            fallback_output=fallback_output,
        )
        if quote is not None:
            cost = round(
                usage.input_tokens / 1_000_000 * quote.input_per_million
                + usage.output_tokens / 1_000_000 * quote.output_per_million,
                6,
            )
            pricing_source = "built-in" if quote.known else "custom fallback"
            model_prices[quote.model] = {
                "model": quote.model,
                "input_per_million": quote.input_per_million,
                "output_per_million": quote.output_per_million,
                "provider": quote.provider,
                "source": quote.source,
                "note": quote.note,
                "known": quote.known,
            }
        else:
            cost = usage.estimated_usd if usage.estimated_usd > 0 else 0.0
            pricing_source = "stored" if cost > 0 else "unpriced"

        estimated_usd += cost
        rows.append(
            {
                "turn": turn.turn,
                "kind": turn.kind,
                "action": turn.action,
                "model": turn.model,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": total,
                "estimated_usd": round(cost, 6),
                "priced": quote is not None or usage.estimated_usd > 0,
                "pricing_source": pricing_source,
                "world_time": turn.world_time_after,
            }
        )

    billable = [row for row in rows if row["total_tokens"] > 0]
    priced = [row for row in billable if row["priced"]]
    return {
        "campaign": {
            "id": state.meta.id,
            "title": state.meta.title,
            "turn_count": state.meta.turn_count,
            "world_time": format_world_time(state.meta.world_time_minutes),
        },
        "totals": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "estimated_usd": round(estimated_usd, 6),
            "turns": len(rows),
            "billable_turns": len(billable),
            "priced_turns": len(priced),
            "average_tokens_per_turn": (
                (input_tokens + output_tokens) // len(billable) if billable else 0
            ),
        },
        "models": sorted(models),
        "model_prices": sorted(model_prices.values(), key=lambda item: item["model"]),
        "turns": rows,
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
        {"id": slug, "name": faction.name}
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
            "description": strip_gm_blocks(state.npc_bodies.get(npc_id, "")),
        }
        for npc_id, npc in state.npcs.items()
        if npc.player_known
    ]

    character = state.character.model_dump(mode="json")
    character["description"] = strip_gm_blocks(state.character_body)
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
            "time_of_day": time_of_day(state.meta.world_time_minutes),
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


def canon_view(state: CampaignState) -> dict[str, Any]:
    """Everything the harness knows, for inspection rather than play."""

    character = state.character.model_dump(mode="json")
    character["description"] = strip_gm_blocks(state.character_body)
    inventory = sorted(
        (
            {"id": slug, **item.model_dump(mode="json")}
            for slug, item in state.character.inventory.items()
        ),
        key=lambda item: item["name"].lower(),
    )
    return {
        "campaign": {
            **state.meta.model_dump(mode="json"),
            "world_time": format_world_time(state.meta.world_time_minutes),
            "time_of_day": time_of_day(state.meta.world_time_minutes),
        },
        "counts": {
            "npcs": len(state.npcs),
            "locations": len(state.world.locations),
            "factions": len(state.world.factions),
            "clocks": len(state.world.clocks),
            "facts": len(state.world.facts),
            "turns": len(state.turns),
        },
        "notes": {
            "campaign": state.campaign_body,
            "character": state.character_body,
            "world": state.world_body,
        },
        "character": character,
        "inventory": inventory,
        "world": {
            "situation": state.world.situation,
            "current_location": state.world.current_location,
            "locations": [
                {"id": slug, **location.model_dump(mode="json")}
                for slug, location in state.world.locations.items()
            ],
            "factions": [
                {"id": slug, **faction.model_dump(mode="json")}
                for slug, faction in state.world.factions.items()
            ],
            "clocks": [
                {"id": slug, **clock.model_dump(mode="json")}
                for slug, clock in state.world.clocks.items()
            ],
            "facts": [fact.model_dump(mode="json") for fact in state.world.facts.values()],
        },
        "npcs": [
            {
                "id": npc_id,
                "sheet": npc.model_dump(mode="json"),
                "notes": state.npc_bodies.get(npc_id, ""),
                "gm_blocks": extract_gm_block_text(state.npc_bodies.get(npc_id, "")),
            }
            for npc_id, npc in state.npcs.items()
        ],
        "journal": state.journal,
        "turns": [turn.model_dump(mode="json") for turn in state.turns],
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
