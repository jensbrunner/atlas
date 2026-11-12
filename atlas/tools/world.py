from __future__ import annotations

from atlas.ids import slugify
from atlas.state.schemas import Location
from atlas.tools._util import as_bool
from atlas.tools.context import ToolContext, ToolError


def handle_set_scene(ctx: ToolContext, args: dict[str, object]) -> str:
    location = slugify(str(args.get("location", "")).strip(), fallback="")
    if not location:
        raise ToolError("location is required")
    if location not in ctx.state.world.locations:
        raise ToolError(f"unknown location {location!r}")

    ctx.state.world.current_location = location
    notes = [f"scene moved to {location}"]

    place = ctx.state.world.locations[location]
    if not place.player_known:
        place.player_known = True
        notes.append("location discovered by the player")

    description = str(args.get("description", "") or "").strip()
    if description:
        place.description = description
        notes.append("location description updated")

    situation = str(args.get("situation", "") or "").strip()
    if situation:
        ctx.state.world.situation = situation
        notes.append("situation updated")

    ctx.changes.extend(notes)
    return "; ".join(notes)


def handle_create_location(ctx: ToolContext, args: dict[str, object]) -> str:
    location_id = slugify(str(args.get("id", "")).strip(), fallback="location")
    if location_id in ctx.state.world.locations:
        raise ToolError(f"location {location_id!r} already exists")
    name = str(args.get("name", "")).strip()
    if not name:
        raise ToolError("location name is required")
    raw_tags = args.get("tags", [])
    tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []

    ctx.state.world.locations[location_id] = Location(
        name=name,
        description=str(args.get("description", "") or "").strip(),
        player_known=as_bool(args.get("player_known"), True),
        tags=tags,
    )
    ctx.note(f"location created: {location_id}")
    return f"Created location {location_id} ({name})."


def handle_reveal_location(ctx: ToolContext, args: dict[str, object]) -> str:
    location_id = slugify(str(args.get("location", "")).strip(), fallback="")
    place = ctx.state.world.locations.get(location_id)
    if place is None:
        raise ToolError(f"unknown location {location_id!r}")
    if place.player_known:
        return f"Location {location_id} is already known to the player."
    place.player_known = True
    ctx.note(f"location revealed: {location_id}")
    return f"Revealed location {location_id} to the player."


def handle_request_world_turn(ctx: ToolContext, args: dict[str, object]) -> str:
    reason = str(args.get("reason", "") or "").strip()
    ctx.world_turn_requested = True
    ctx.note(f"world turn requested{f': {reason}' if reason else ''}")
    return "World turn queued; it will run after this turn is committed."
