from __future__ import annotations

from atlas.ids import slugify
from atlas.state.schemas import Clock, Fact
from atlas.tools._util import as_int
from atlas.tools.context import ToolContext, ToolError


def _complete_clock(
    ctx: ToolContext,
    clock_id: str,
    clock: Clock,
    message: str,
) -> str:
    trigger = clock.trigger.strip() or "the pressure resolves."
    base = f"fact_clock_{slugify(clock_id)}"
    fact_id = base
    suffix = 2
    while fact_id in ctx.state.world.facts:
        fact_id = f"{base}_{suffix}"
        suffix += 1
    ctx.state.world.facts[fact_id] = Fact(
        id=fact_id,
        text=f"{clock.name} reached its end: {trigger}",
        visibility=clock.visibility,
        tags=["clock"],
    )
    del ctx.state.world.clocks[clock_id]
    ctx.note(f"clock resolved: {clock_id}")
    return (
        f"{message}. The clock is full and resolved; its trigger is recorded "
        f"as {fact_id}: {trigger}"
    )


def handle_patch_clock(ctx: ToolContext, args: dict[str, object]) -> str:
    clock_id = slugify(str(args.get("clock", "")).strip())
    delta = as_int(args.get("delta"), 0)
    reason = str(args.get("reason", "")).strip()
    clock = ctx.state.world.clocks.get(clock_id)
    if clock is None:
        raise ToolError(f"unknown clock {clock_id!r}")
    if delta == 0:
        raise ToolError("clock delta cannot be zero")

    before = clock.filled
    clock.filled = max(0, min(clock.segments, before + delta))
    message = f"clock {clock_id} {before}->{clock.filled}/{clock.segments}"
    if reason:
        message += f" ({reason})"
    ctx.note(message)
    if clock.filled == clock.segments:
        return _complete_clock(ctx, clock_id, clock, message)
    return message


def handle_create_clock(ctx: ToolContext, args: dict[str, object]) -> str:
    clock_id = slugify(str(args.get("id", "")).strip(), fallback="clock")
    if clock_id in ctx.state.world.clocks:
        raise ToolError(f"clock {clock_id!r} already exists")
    name = str(args.get("name", "")).strip() or clock_id.replace("_", " ").title()
    segments = as_int(args.get("segments"), 4)
    if segments < 1 or segments > 20:
        raise ToolError("clock segments must be between 1 and 20")
    visibility = str(args.get("visibility", "player"))
    if visibility not in {"gm", "player"}:
        raise ToolError("clock visibility must be 'gm' or 'player'")
    ctx.state.world.clocks[clock_id] = Clock(
        name=name,
        segments=segments,
        filled=0,
        trigger=str(args.get("trigger", "")),
        visibility=visibility,  # type: ignore[arg-type]
    )
    ctx.note(f"clock created: {clock_id} ({segments})")
    return f"Created clock {clock_id} with {segments} segments."
