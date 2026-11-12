from __future__ import annotations

from atlas.retrieval import Doc, DocKind, RetrievalIndex
from atlas.state.schemas import CampaignState
from atlas.tools._util import as_int
from atlas.tools.context import ToolContext, ToolError

_KINDS: dict[str, DocKind | None] = {
    "any": None,
    "npc": "npc",
    "location": "location",
    "faction": "faction",
    "fact": "fact",
    "clock": "clock",
}


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _render(state: CampaignState, doc: Doc) -> str:
    if doc.kind == "npc":
        npc = state.npcs.get(doc.id)
        if npc is None:
            return ""
        body = _clip(state.npc_bodies.get(doc.id, ""), 500)
        known = []
        for fact_id in npc.knows[:5]:
            fact = state.world.facts.get(fact_id)
            if fact is not None:
                known.append(f"{fact_id}: {_clip(fact.text, 160)}")
        return "\n".join(
            [
                f"[npc] {npc.id} — {npc.name} (at {npc.location or 'unknown'}; "
                f"player-known: {npc.player_known})",
                f"  attitude: {_clip(npc.attitude, 200)}",
                f"  goals: {'; '.join(npc.goals) or 'none'}",
                f"  plans: {'; '.join(npc.plans[-3:]) or 'none'}",
                f"  knows: {'; '.join(known) or ', '.join(npc.knows) or 'nothing recorded'}",
                f"  notes: {body or 'none'}",
            ]
        )
    if doc.kind == "location":
        location = state.world.locations.get(doc.id)
        if location is None:
            return ""
        return (
            f"[location] {doc.id} — {location.name} "
            f"(player-known: {location.player_known}): {location.description}"
        )
    if doc.kind == "faction":
        faction = state.world.factions.get(doc.id)
        if faction is None:
            return ""
        return (
            f"[faction] {doc.id} — {faction.name} "
            f"(player-known: {faction.player_known}); goal: {faction.goal}; "
            f"stance: {faction.stance}; resources: {faction.resources}"
        )
    if doc.kind == "clock":
        clock = state.world.clocks.get(doc.id)
        if clock is None:
            return ""
        return (
            f"[clock] {doc.id} — {clock.name}: {clock.filled}/{clock.segments} "
            f"(visibility: {clock.visibility}); trigger: {clock.trigger}"
        )
    fact = state.world.facts.get(doc.id)
    if fact is None:
        return ""
    return f"[fact] {fact.id} [{fact.visibility}] {fact.text}"


def handle_lookup_canon(ctx: ToolContext, args: dict[str, object]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("query is required")
    kind_arg = str(args.get("kind", "any")).strip().lower()
    if kind_arg not in _KINDS:
        raise ToolError("kind must be any, npc, location, faction, fact, or clock")
    limit = max(1, min(12, as_int(args.get("limit"), 6)))

    index = RetrievalIndex(ctx.state)
    matches = index.search(query, kind=_KINDS[kind_arg], limit=limit)
    if not matches:
        return (
            f"No canon matches for {query!r}. Try a name, place, or distinctive keyword; "
            "do not invent a replacement without recording it."
        )

    rendered = [line for _, doc in matches if (line := _render(ctx.state, doc))]
    header = f"Canon lookup for {query!r} ({len(rendered)} matches):"
    return "\n".join([header, *rendered])
