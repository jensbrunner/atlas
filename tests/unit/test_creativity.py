from __future__ import annotations

from atlas.creativity import choose_narrative_lens, make_creative_brief


def test_brief_contains_all_ingredients() -> None:
    brief = make_creative_brief()
    prompt = brief.as_prompt()
    for value in (
        brief.setting,
        brief.relationship,
        brief.opening,
        brief.pressure,
        brief.texture,
        brief.wildcard,
    ):
        assert value
        assert value in prompt
    assert "Connect at least three" in prompt


def test_briefs_are_not_a_fixed_sequence() -> None:
    prompts = {make_creative_brief().as_prompt() for _ in range(20)}
    assert len(prompts) > 1


def test_narrative_lens_avoids_recent_choices() -> None:
    recent = [
        "a small object changes hands",
        "a sound from outside the scene",
        "a smell tied to a particular person or place",
        "a routine task is interrupted",
    ]
    for _ in range(20):
        lens = choose_narrative_lens(recent)
        assert lens not in recent
