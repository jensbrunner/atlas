from __future__ import annotations

from atlas.retrieval import Selection, select_context
from atlas.state.schemas import CampaignState
from atlas.state.store import format_world_time, time_of_day


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def campaign_section(state: CampaignState) -> str:
    lines = [
        f"Title: {state.meta.title}",
        f"Genre: {state.meta.genre or 'unspecified'}",
        f"Tone: {state.meta.tone or 'unspecified'}",
        f"Premise: {state.meta.premise}",
    ]
    if state.campaign_body.strip():
        lines.append(f"Notes: {_clip(state.campaign_body, 2_000)}")
    return "\n".join(lines)


def character_sheet(state: CampaignState) -> str:
    character = state.character
    inventory = (
        ", ".join(
            f"{item.name} x{item.quantity}"
            for item in sorted(character.inventory.values(), key=lambda i: i.name)
        )
        or "nothing"
    )
    conditions = ", ".join(character.conditions) or "none"
    skills = (
        ", ".join(f"{name} {value:+d}" for name, value in sorted(character.skills.items()))
        or "none"
    )
    return "\n".join(
        [
            f"Name: {character.name}",
            f"Concept: {character.concept or 'unspecified'}",
            (
                f"Attributes: Might {character.attributes.might:+d}, "
                f"Agility {character.attributes.agility:+d}, "
                f"Insight {character.attributes.insight:+d}, "
                f"Presence {character.attributes.presence:+d}"
            ),
            f"Skills: {skills}",
            (
                f"Health: {character.health.current}/{character.health.max}; "
                f"Stress: {character.stress.current}/{character.stress.max}; "
                f"Supplies: {character.supplies}; Currency: {character.currency}"
            ),
            f"Conditions: {conditions}",
            f"Inventory: {inventory}",
            (
                f"Background: {_clip(state.character_body, 1_500)}"
                if state.character_body.strip()
                else "Background: unspecified"
            ),
        ]
    )


def _npc_sheet(state: CampaignState, npc_id: str) -> str:
    npc = state.npcs[npc_id]
    body = state.npc_bodies.get(npc_id, "").strip()
    location = npc.location or "unknown"
    known = ", ".join(npc.knows) or "none"
    goals = "; ".join(npc.goals) or "none"
    plans = "; ".join(npc.plans[-3:]) or "none"
    lines = [
        f"### {npc.name} ({npc_id})",
        f"Location: {location}; attitude: {npc.attitude}; player-known: {npc.player_known}",
        f"Health: {npc.health.current}/{npc.health.max}; goals: {goals}",
        f"Current plans: {plans}",
        f"Knows facts: {known}",
    ]
    if body:
        lines.append(_clip(body, 1_200))
    return "\n".join(lines)


def world_section(state: CampaignState, selection: Selection | None = None) -> str:
    world = state.world
    location_ids = selection.locations if selection else list(world.locations)
    faction_ids = selection.factions if selection else list(world.factions)
    clock_ids = selection.clocks if selection else list(world.clocks)
    fact_ids = selection.facts if selection else list(world.facts)

    locations = "\n".join(
        f"- {slug} — {world.locations[slug].name} "
        f"(player-known: {world.locations[slug].player_known}): "
        f"{world.locations[slug].description}"
        for slug in location_ids
        if slug in world.locations
    )
    factions = "\n".join(
        (
            f"- {slug} — {world.factions[slug].name} "
            f"(player-known: {world.factions[slug].player_known}); "
            f"goal: {world.factions[slug].goal}; stance: {world.factions[slug].stance}; "
            f"resources: {world.factions[slug].resources}"
        )
        for slug in faction_ids
        if slug in world.factions
    )
    clocks = "\n".join(
        (
            f"- {slug} — {world.clocks[slug].name}: "
            f"{world.clocks[slug].filled}/{world.clocks[slug].segments} "
            f"(visibility: {world.clocks[slug].visibility}); "
            f"trigger: {world.clocks[slug].trigger}"
        )
        for slug in clock_ids
        if slug in world.clocks
    )
    facts = "\n".join(
        f"- {fact_id} [{world.facts[fact_id].visibility}] {world.facts[fact_id].text}"
        for fact_id in fact_ids
        if fact_id in world.facts
    )

    packet_npcs = (
        selection.npcs
        if selection
        else [
            npc_id for npc_id, npc in state.npcs.items() if npc.location == world.current_location
        ]
    )
    present = [
        state.npcs[npc_id].name
        for npc_id in packet_npcs
        if npc_id in state.npcs and state.npcs[npc_id].location == world.current_location
    ]
    all_present = [npc for npc in state.npcs.values() if npc.location == world.current_location]
    location = world.locations.get(world.current_location)
    lines = [
        f"Current location: {world.current_location}" + (f" — {location.name}" if location else ""),
        f"World time: {format_world_time(state.meta.world_time_minutes)} "
        f"({time_of_day(state.meta.world_time_minutes)}; "
        f"{state.meta.world_time_minutes} minutes)",
        f"NPCs present: {', '.join(present) if present else 'none'}",
        f"Situation: {world.situation}",
    ]
    if selection is not None:
        lines.extend(
            [
                f"Context packet: {selection.packet_line()}.",
                "Canon not listed above is still binding. If you need an omitted "
                "person, place, faction, fact, or clock, call `lookup_canon` with a "
                "name or keyword before using it. Do not contradict omitted canon.",
            ]
        )
        if len(all_present) > len(present):
            lines.append(
                f"Other people are present but omitted from the packet: "
                f"{len(all_present) - len(present)}. Use `lookup_canon` if the scene "
                "turns to them."
            )
    lines.extend(
        [
            "",
            "Locations:",
            locations or "- none",
            "",
            "Factions:",
            factions or "- none",
            "",
            "Clocks:",
            clocks or "- none",
            "",
            "Facts (GM canon; 'gm' facts are secret):",
            facts or "- none",
        ]
    )
    if state.world_body.strip():
        lines.extend(["", "World notes:", _clip(state.world_body, 4_000)])
    return "\n".join(lines)


def recent_turns(state: CampaignState, limit: int) -> str:
    if limit <= 0:
        return ""
    turns = state.turns[-limit:]
    blocks: list[str] = []
    for turn in turns:
        heading = "Opening" if turn.kind == "opening" else f"Turn {turn.turn} ({turn.kind})"
        block = [f"### {heading} — {format_world_time(turn.world_time_after)}"]
        if turn.action and turn.kind == "player":
            block.append(f"Player: {turn.action}")
        block.append(_clip(turn.narration, 1_200))
        if turn.rolls:
            block.append(
                "Rolls: "
                + "; ".join(
                    f"{roll.label}{f' ({roll.check})' if roll.check else ''} "
                    f"{roll.dice[0]}+{roll.dice[1]}{roll.modifier:+d}"
                    f"={roll.total} vs {roll.difficulty} ({roll.outcome})"
                    for roll in turn.rolls
                )
            )
        blocks.append("\n".join(block))
    return "\n\n".join(blocks)


def _fit_prompt(head: str, tail: str, char_budget: int) -> str:
    """Trim context while always preserving the action and instructions."""

    tail = tail.strip()
    if len(tail) >= char_budget:
        return tail[-char_budget:]
    head = head.strip()
    available = char_budget - len(tail) - 2
    if len(head) > available:
        head = head[: max(0, available - 2)].rstrip() + "\n…"
    return f"{head}\n\n{tail}" if head else tail


def build_turn_prompt(
    state: CampaignState,
    action: str,
    *,
    recent_turn_limit: int = 6,
    char_budget: int = 48_000,
    narrative_lens: str = "",
) -> str:
    selection = select_context(state, action, mode="narrator")
    npcs = (
        "\n\n".join(_npc_sheet(state, npc_id) for npc_id in selection.npcs if npc_id in state.npcs)
        or "No NPCs are defined yet."
    )
    head = "\n".join(
        [
            "# Campaign",
            campaign_section(state),
            "",
            "# Player character",
            character_sheet(state),
            "",
            "# World",
            world_section(state, selection),
            "",
            "# NPCs (GM view)",
            npcs,
            "",
            "# Recent turns",
            recent_turns(state, recent_turn_limit) or "This is the first player turn.",
        ]
    )
    tail_parts: list[str] = []
    if narrative_lens.strip():
        tail_parts.extend(
            [
                "# Optional creative texture for this turn",
                narrative_lens.strip(),
                "Weave this in naturally if it fits the scene. Do not mention this "
                "instruction or force it.",
                "",
            ]
        )
    tail_parts.extend(
        [
            "# Player action",
            action.strip(),
            "",
            (
                "Narrate the outcome of this action. Use tools for every mechanical or "
                "persistent change. Do not decide the player character's voluntary speech, "
                "thoughts, or additional actions. Do not reveal secret facts. End with "
                "player-facing narration only."
            ),
        ]
    )
    tail = "\n".join(tail_parts)
    return _fit_prompt(head, tail, char_budget)


def build_world_prompt(state: CampaignState, reason: str, *, char_budget: int = 32_000) -> str:
    selection = select_context(
        state,
        f"{reason} {state.turns[-1].narration[:800] if state.turns else ''}",
        mode="world",
    )
    head = "\n".join(
        [
            "# World evolution request",
            f"Reason: {reason or 'time has passed and the world should move on its own.'}",
            "",
            "# Campaign",
            campaign_section(state),
            "",
            "# World",
            world_section(state, selection),
            "",
            "# NPCs (GM view)",
            "\n\n".join(
                _npc_sheet(state, npc_id) for npc_id in selection.npcs if npc_id in state.npcs
            )
            or "- none",
            "",
            "# Recent turns",
            recent_turns(state, 4) or "No turns yet.",
        ]
    )
    tail = (
        "Update the offscreen world: advance clocks when pressure has built, let "
        "factions and NPCs pursue their goals, and record any new canonical facts. "
        "Use tools only. Do not write player-facing prose. Finish with a brief "
        "GM-facing summary of what changed offscreen."
    )
    return _fit_prompt(head, tail, char_budget)


def build_audit_prompt(state: CampaignState, *, char_budget: int = 40_000) -> str:
    selection = select_context(
        state,
        " ".join(turn.narration[:900] for turn in state.turns[-3:]) or "continuity audit",
        mode="audit",
    )
    head = "\n".join(
        [
            "# Continuity audit",
            campaign_section(state),
            "",
            "# Player character",
            character_sheet(state),
            "",
            "# World canon",
            world_section(state, selection),
            "",
            "# NPCs",
            "\n\n".join(
                _npc_sheet(state, npc_id) for npc_id in selection.npcs if npc_id in state.npcs
            )
            or "- none",
            "",
            "# Recent turns",
            recent_turns(state, 12) or "No turns yet.",
        ]
    )
    tail = (
        "Find contradictions with established canon, impossible state, or facts that "
        "were revealed before they should have been. Report only concrete problems "
        "with evidence. Return an empty findings list if nothing is wrong."
    )
    return _fit_prompt(head, tail, char_budget)
