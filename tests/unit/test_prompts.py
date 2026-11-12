from __future__ import annotations

from atlas.agents.prompts import load_prompt


def test_campaign_prompt_does_not_default_to_waterfronts() -> None:
    prompt = load_prompt("campaign").casefold()
    for word in ("tide", "harbor", "harbour", "dock", "sluice", "wharf", "quay"):
        assert word not in prompt


def test_narrator_prompt_does_not_steer_toward_tide_imagery() -> None:
    prompt = load_prompt("narrator").casefold()
    assert "tide" not in prompt
