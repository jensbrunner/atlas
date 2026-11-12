from __future__ import annotations

from random import Random

from atlas.state.schemas import Attributes, RollRecord
from atlas.tools._util import as_int
from atlas.tools.context import ToolContext, ToolError

ATTRIBUTES = ("might", "agility", "insight", "presence")


def resolve_roll(
    *,
    rng: Random,
    label: str,
    attribute: str,
    attribute_value: int,
    skill: str = "",
    skill_value: int,
    bonus: int,
    difficulty: int,
) -> RollRecord:
    if attribute not in ATTRIBUTES:
        raise ToolError(f"unknown attribute {attribute!r}; use one of {', '.join(ATTRIBUTES)}")
    if difficulty < 2 or difficulty > 20:
        raise ToolError("difficulty must be between 2 and 20")

    dice = [rng.randint(1, 6), rng.randint(1, 6)]
    modifier = attribute_value + skill_value + bonus
    total = sum(dice) + modifier
    if total >= difficulty + 2:
        outcome = "success"
    elif total >= difficulty:
        outcome = "mixed_success"
    else:
        outcome = "failure"
    return RollRecord(
        label=label,
        attribute=attribute,
        skill=skill,
        attribute_value=attribute_value,
        skill_value=skill_value,
        bonus=bonus,
        dice=dice,
        modifier=modifier,
        difficulty=difficulty,
        total=total,
        outcome=outcome,
    )


def handle_roll(ctx: ToolContext, args: dict[str, object]) -> str:
    label = str(args.get("label", "check")).strip() or "check"
    attribute = str(args.get("attribute", "insight"))
    skill = str(args.get("skill", "")).strip()
    difficulty = as_int(args.get("difficulty"), 8)
    bonus = as_int(args.get("modifier"), 0)

    attributes = ctx.state.character.attributes
    if not isinstance(attributes, Attributes):
        raise ToolError("character attributes are invalid")
    attribute_value = getattr(attributes, attribute, None)
    if attribute_value is None:
        raise ToolError(f"unknown attribute {attribute!r}")
    skill_value = int(ctx.state.character.skills.get(skill, 0)) if skill else 0

    record = resolve_roll(
        rng=ctx.rng,
        label=label,
        attribute=attribute,
        attribute_value=int(attribute_value),
        skill=skill,
        skill_value=skill_value,
        bonus=bonus,
        difficulty=difficulty,
    )
    ctx.rolls.append(record)
    descriptor = attribute.title()
    if skill:
        descriptor += f" + {skill}"
    ctx.note(
        f"rolled {record.label} ({descriptor}): "
        f"{record.dice[0]}+{record.dice[1]}{record.modifier:+d}"
        f" = {record.total} vs {record.difficulty} ({record.outcome})"
    )
    return (
        f"{record.outcome}. {descriptor}: {record.dice[0]}+{record.dice[1]}"
        f"{record.modifier:+d} = {record.total} against difficulty {record.difficulty}."
    )
