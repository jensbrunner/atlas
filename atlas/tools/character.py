from __future__ import annotations

from atlas.tools._util import as_int
from atlas.tools.context import ToolContext, ToolError


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def handle_patch_character(ctx: ToolContext, args: dict[str, object]) -> str:
    character = ctx.state.character
    notes: list[str] = []

    health_delta = as_int(args.get("health_delta"), 0)
    if health_delta:
        before = character.health.current
        character.health.current = _clamp(before + health_delta, 0, character.health.max)
        notes.append(f"health {before}->{character.health.current}")

    stress_delta = as_int(args.get("stress_delta"), 0)
    if stress_delta:
        before = character.stress.current
        character.stress.current = _clamp(before + stress_delta, 0, character.stress.max)
        notes.append(f"stress {before}->{character.stress.current}")

    supplies_delta = as_int(args.get("supplies_delta"), 0)
    if supplies_delta:
        before = character.supplies
        if before + supplies_delta < 0:
            raise ToolError("character cannot spend more supplies than they carry")
        character.supplies = before + supplies_delta
        notes.append(f"supplies {before}->{character.supplies}")

    currency_delta = as_int(args.get("currency_delta"), 0)
    if currency_delta:
        before = character.currency
        if before + currency_delta < 0:
            raise ToolError("character cannot spend more currency than they carry")
        character.currency = before + currency_delta
        notes.append(f"currency {before}->{character.currency}")

    add_condition = str(args.get("add_condition") or "").strip()
    if add_condition and add_condition not in character.conditions:
        character.conditions.append(add_condition)
        notes.append(f"condition added: {add_condition}")

    remove_condition = str(args.get("remove_condition") or "").strip()
    if remove_condition:
        if remove_condition not in character.conditions:
            raise ToolError(f"character does not have condition {remove_condition!r}")
        character.conditions.remove(remove_condition)
        notes.append(f"condition removed: {remove_condition}")

    if not notes:
        return "No character change requested."
    ctx.changes.extend(notes)
    return "; ".join(notes)
