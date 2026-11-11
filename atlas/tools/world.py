from __future__ import annotations

from atlas.ids import slugify
from atlas.tools.context import ToolContext, ToolError


def handle_set_scene(ctx: ToolContext, args: dict[str, object]) -> str:
    location = slugify(str(args.get("location", "")).strip(), fallback="")
    if not location:
        raise ToolError("location is required")
    if location not in ctx.state.world.locations:
        raise ToolError(f"unknown location {location!r}")

    ctx.state.world.current_location = location
    notes = [f"scene moved to {location}"]

    description = str(args.get("description", "") or "").strip()
    if description:
        ctx.state.world.locations[location].description = description
        notes.append("location description updated")

    situation = str(args.get("situation", "") or "").strip()
    if situation:
        ctx.state.world.situation = situation
        notes.append("situation updated")

    ctx.changes.extend(notes)
    return "; ".join(notes)


def handle_request_world_turn(ctx: ToolContext, args: dict[str, object]) -> str:
    reason = str(args.get("reason", "") or "").strip()
    ctx.world_turn_requested = True
    ctx.note(f"world turn requested{f': {reason}' if reason else ''}")
    return "World turn queued; it will run after this turn is committed."
