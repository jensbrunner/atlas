from __future__ import annotations

from atlas.ids import slugify
from atlas.state.schemas import Fact
from atlas.tools.context import ToolContext, ToolError


def _unique_fact_id(ctx: ToolContext, text: str) -> str:
    base = f"fact_{slugify(text)[:48]}"
    candidate = base
    index = 2
    while candidate in ctx.state.world.facts:
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def handle_record_fact(ctx: ToolContext, args: dict[str, object]) -> str:
    text = str(args.get("text", "")).strip()
    if not text:
        raise ToolError("fact text is required")
    visibility = str(args.get("visibility", "gm"))
    if visibility not in {"gm", "player"}:
        raise ToolError("fact visibility must be 'gm' or 'player'")
    raw_tags = args.get("tags", [])
    tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []
    fact_id = _unique_fact_id(ctx, text)
    ctx.state.world.facts[fact_id] = Fact(
        id=fact_id,
        text=text,
        visibility=visibility,  # type: ignore[arg-type]
        tags=tags,
    )
    ctx.note(f"fact recorded: {fact_id} ({visibility})")
    return f"Recorded fact {fact_id} with {visibility} visibility."


def handle_reveal_fact(ctx: ToolContext, args: dict[str, object]) -> str:
    fact_id = str(args.get("fact", "")).strip()
    fact = ctx.state.world.facts.get(fact_id)
    if fact is None:
        raise ToolError(f"unknown fact {fact_id!r}")
    if fact.visibility == "player":
        return f"Fact {fact_id} is already player-visible."
    fact.visibility = "player"
    fact.revealed_at_turn = ctx.state.meta.turn_count + 1
    ctx.note(f"fact revealed: {fact_id}")
    return f"Revealed {fact_id} to the player."


def handle_append_journal(ctx: ToolContext, args: dict[str, object]) -> str:
    text = str(args.get("text", "")).strip()
    if not text:
        raise ToolError("journal text is required")
    heading = str(args.get("heading", "")).strip()
    block = f"### {heading}\n\n{text}" if heading else text
    ctx.state.journal = f"{ctx.state.journal.rstrip()}\n\n{block}".strip()
    ctx.note("journal entry appended")
    return "Journal entry appended."
