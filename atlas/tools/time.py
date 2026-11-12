from __future__ import annotations

from atlas.state.store import format_world_time
from atlas.tools._util import as_int
from atlas.tools.context import ToolContext, ToolError


def handle_advance_time(ctx: ToolContext, args: dict[str, object]) -> str:
    minutes = as_int(args.get("minutes"), 0)
    reason = str(args.get("reason", "")).strip()
    if minutes <= 0:
        raise ToolError("minutes must be a positive integer")
    if minutes > 60 * 24 * 30:
        raise ToolError("a single time advance is limited to 30 in-world days")
    if ctx.time_advanced:
        raise ToolError(
            "advance_time may be called only once per turn; combine the elapsed "
            "time into a single call"
        )

    before = ctx.state.meta.world_time_minutes
    ctx.state.meta.world_time_minutes = before + minutes
    ctx.time_advanced = True
    ctx.note(f"world time +{minutes}m -> {format_world_time(ctx.state.meta.world_time_minutes)}")
    suffix = f" ({reason})" if reason else ""
    now = format_world_time(ctx.state.meta.world_time_minutes)
    return f"Advanced {minutes} minutes{suffix}; it is now {now}."
