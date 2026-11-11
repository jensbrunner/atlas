from __future__ import annotations

from atlas.state.schemas import CampaignState


class InvalidState(Exception):
    """Raised when a campaign state violates structural or numeric bounds."""


def validate_state(state: CampaignState) -> None:
    world = state.world
    character = state.character

    if not world.locations:
        raise InvalidState("campaign has no locations")
    if world.current_location and world.current_location not in world.locations:
        raise InvalidState(f"current location {world.current_location!r} does not exist")

    if character.health.current < 0 or character.health.current > character.health.max:
        raise InvalidState("character health is out of bounds")
    if character.stress.current < 0 or character.stress.current > character.stress.max:
        raise InvalidState("character stress is out of bounds")
    if character.supplies < 0 or character.currency < 0:
        raise InvalidState("character supplies and currency must be non-negative")

    for slug, item in character.inventory.items():
        if item.quantity < 0:
            raise InvalidState(f"inventory item {slug!r} has negative quantity")

    for clock_id, clock in world.clocks.items():
        if clock.filled < 0 or clock.filled > clock.segments:
            raise InvalidState(f"clock {clock_id!r} is out of bounds")

    for fact_id, fact in world.facts.items():
        if not fact.text.strip():
            raise InvalidState(f"fact {fact_id!r} is empty")

    for npc_id, npc in state.npcs.items():
        if npc.location and npc.location not in world.locations:
            raise InvalidState(f"npc {npc_id!r} is in unknown location {npc.location!r}")
        if npc.health.current < 0 or npc.health.current > npc.health.max:
            raise InvalidState(f"npc {npc_id!r} health is out of bounds")
        missing = [fact for fact in npc.knows if fact not in world.facts]
        if missing:
            raise InvalidState(f"npc {npc_id!r} knows unknown facts: {missing}")

    if state.meta.world_time_minutes < 0:
        raise InvalidState("world time cannot be negative")
    if state.meta.turn_count < 0:
        raise InvalidState("turn count cannot be negative")
