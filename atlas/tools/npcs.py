from __future__ import annotations

from atlas.ids import slugify
from atlas.tools._util import as_int
from atlas.tools.context import ToolContext, ToolError


def handle_update_npc(ctx: ToolContext, args: dict[str, object]) -> str:
    npc_id = slugify(str(args.get("npc", "")).strip(), fallback="npc")
    npc = ctx.state.npcs.get(npc_id)
    if npc is None:
        raise ToolError(f"unknown npc {npc_id!r}")

    notes: list[str] = []
    location = str(args.get("location", "") or "").strip()
    if location:
        location_id = slugify(location)
        if location_id not in ctx.state.world.locations:
            raise ToolError(f"unknown location {location_id!r}")
        npc.location = location_id
        notes.append(f"{npc_id} moved to {location_id}")

    attitude = str(args.get("attitude", "") or "").strip()
    if attitude:
        npc.attitude = attitude
        notes.append(f"{npc_id} attitude -> {attitude}")

    goal = str(args.get("add_goal", "") or "").strip()
    if goal:
        npc.goals.append(goal)
        notes.append(f"{npc_id} goal added")

    knowledge = str(args.get("add_knowledge", "") or "").strip()
    if knowledge:
        if knowledge not in ctx.state.world.facts:
            raise ToolError(f"unknown fact {knowledge!r}")
        if knowledge not in npc.knows:
            npc.knows.append(knowledge)
            notes.append(f"{npc_id} learns {knowledge}")

    health_delta = as_int(args.get("health_delta"), 0)
    if health_delta:
        before = npc.health.current
        npc.health.current = max(0, min(npc.health.max, before + health_delta))
        notes.append(f"{npc_id} health {before}->{npc.health.current}")

    if not notes:
        return "No NPC change requested."
    ctx.changes.extend(notes)
    return "; ".join(notes)


def handle_update_faction(ctx: ToolContext, args: dict[str, object]) -> str:
    faction_id = slugify(str(args.get("faction", "")).strip(), fallback="faction")
    faction = ctx.state.world.factions.get(faction_id)
    if faction is None:
        raise ToolError(f"unknown faction {faction_id!r}")

    notes: list[str] = []
    goal = str(args.get("goal", "") or "").strip()
    if goal:
        faction.goal = goal
        notes.append(f"{faction_id} goal updated")

    stance = str(args.get("stance", "") or "").strip()
    if stance:
        faction.stance = stance
        notes.append(f"{faction_id} stance -> {stance}")

    resource = str(args.get("resource", "") or "").strip()
    delta = as_int(args.get("resource_delta"), 0)
    if resource and delta:
        before = faction.resources.get(resource, 0)
        faction.resources[resource] = before + delta
        notes.append(f"{faction_id} {resource} {before}->{faction.resources[resource]}")

    if not notes:
        return "No faction change requested."
    ctx.changes.extend(notes)
    return "; ".join(notes)
