from __future__ import annotations

import random

from atlas.tools.dice import resolve_roll


class FixedRng(random.Random):
    def __init__(self, values: list[int]) -> None:
        super().__init__(0)
        self._values = values

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002
        return self._values.pop(0)


def _roll(values: list[int], *, modifier: int = 0, difficulty: int = 8) -> str:
    record = resolve_roll(
        rng=FixedRng(values),
        label="test",
        attribute="agility",
        attribute_value=modifier,
        skill_value=0,
        bonus=0,
        difficulty=difficulty,
    )
    return record.outcome


def test_success_when_total_beats_difficulty_by_two() -> None:
    assert _roll([6, 6], modifier=0, difficulty=10) == "success"


def test_mixed_success_at_difficulty() -> None:
    assert _roll([4, 4], modifier=0, difficulty=8) == "mixed_success"


def test_failure_below_difficulty() -> None:
    assert _roll([1, 2], modifier=0, difficulty=8) == "failure"


def test_modifier_is_attribute_plus_skill() -> None:
    record = resolve_roll(
        rng=FixedRng([2, 3]),
        label="test",
        attribute="insight",
        attribute_value=2,
        skill="lore",
        skill_value=2,
        bonus=1,
        difficulty=8,
    )
    assert record.attribute == "insight"
    assert record.skill == "lore"
    assert record.attribute_value == 2
    assert record.skill_value == 2
    assert record.bonus == 1
    assert record.check == "Insight + lore"
    assert record.modifier == 5
    assert record.total == 10
    assert record.outcome == "success"


def test_unknown_attribute_is_rejected() -> None:
    import pytest

    from atlas.tools.context import ToolError

    with pytest.raises(ToolError):
        resolve_roll(
            rng=FixedRng([1, 1]),
            label="test",
            attribute="luck",
            attribute_value=0,
            skill_value=0,
            bonus=0,
            difficulty=8,
        )
