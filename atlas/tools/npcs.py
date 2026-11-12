from __future__ import annotations

from atlas.ids import slugify
from atlas.state.markdown import gm_block
from atlas.state.schemas import NPC, Track
from atlas.tools._util import as_bool, as_int
from atlas.tools.context import ToolContext, ToolError


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


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

    plan = str(args.get("add_plan", "") or "").strip()
    if plan:
        npc.plans.append(plan)
        notes.append(f"{npc_id} plan added")

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


def handle_create_npc(ctx: ToolContext, args: dict[str, object]) -> str:
    npc_id = slugify(
        str(args.get("id", "") or args.get("name", "")).strip(),
        fallback="npc",
    )
    if npc_id in ctx.state.npcs:
        raise ToolError(f"npc {npc_id!r} already exists")
    name = str(args.get("name", "")).strip()
    if not name:
        raise ToolError("npc name is required")

    location = ""
    raw_location = str(args.get("location", "") or "").strip()
    if raw_location:
        location = slugify(raw_location)
        if location not in ctx.state.world.locations:
            raise ToolError(f"unknown location {location!r}")

    knows = _string_list(args.get("knows", []))
    missing = [fact for fact in knows if fact not in ctx.state.world.facts]
    if missing:
        raise ToolError(f"unknown facts: {missing}; record facts before assigning them")

    health_max = max(1, min(20, as_int(args.get("health_max"), 6)))
    ctx.state.npcs[npc_id] = NPC(
        id=npc_id,
        name=name,
        location=location,
        player_known=as_bool(args.get("player_known"), True),
        attitude=str(args.get("attitude", "") or "neutral"),
        goals=_string_list(args.get("goals", [])),
        plans=_string_list(args.get("plans", [])),
        knows=knows,
        health=Track(current=health_max, max=health_max),
    )

    description = str(args.get("description", "") or args.get("appearance", "") or "").strip()
    secret = str(args.get("secret", "") or "").strip()
    body = description
    if secret:
        body = f"{body}\n\n{gm_block(secret)}".strip()
    ctx.state.npc_bodies[npc_id] = body
    ctx.note(f"npc created: {npc_id}")
    return f"Created NPC {npc_id} ({name})."


def handle_reveal_npc(ctx: ToolContext, args: dict[str, object]) -> str:
    npc_id = slugify(str(args.get("npc", "")).strip(), fallback="npc")
    npc = ctx.state.npcs.get(npc_id)
    if npc is None:
        raise ToolError(f"unknown npc {npc_id!r}")
    if npc.player_known:
        return f"NPC {npc_id} is already known to the player."
    npc.player_known = True
    ctx.note(f"npc revealed: {npc_id}")
    return f"Revealed NPC {npc_id} to the player."


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


def handle_reveal_faction(ctx: ToolContext, args: dict[str, object]) -> str:
    faction_id = slugify(str(args.get("faction", "")).strip(), fallback="faction")
    faction = ctx.state.world.factions.get(faction_id)
    if faction is None:
        raise ToolError(f"unknown faction {faction_id!r}")
    if faction.player_known:
        return f"Faction {faction_id} is already known to the player."
    faction.player_known = True
    ctx.note(f"faction revealed: {faction_id}")
    return f"Revealed faction {faction_id} to the player."
