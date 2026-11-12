from __future__ import annotations

from collections import deque
from typing import Any

from atlas.agents.campaign import CampaignGenerator, CampaignRequest
from atlas.agents.types import StructuredRequest
from atlas.config import Settings
from atlas.state.schemas import Usage
from tests.support import seed_payload


class SequenceProvider:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = deque(payloads)
        self.requests: list[StructuredRequest] = []

    def generate_structured(self, request: StructuredRequest) -> tuple[dict[str, Any], Usage]:
        self.requests.append(request)
        return self.payloads.popleft(), Usage(input_tokens=1, output_tokens=1)

    def complete(self, request: Any) -> Any:  # pragma: no cover - not used here
        raise AssertionError("campaign generation should not use complete")


def _mountain_payload() -> dict[str, Any]:
    payload = seed_payload()
    payload.update(
        {
            "title": "The High Observatory",
            "premise": (
                "A mountain observatory where the winter crew has lost contact with the valley."
            ),
            "opening_scene": "At dusk, snow is banked against the observatory doors.",
            "current_location": "observatory",
            "locations": [
                {
                    "id": "observatory",
                    "name": "The Observatory",
                    "description": "A stone dome above the snow line.",
                    "player_known": True,
                }
            ],
            "factions": [],
            "npcs": [
                {
                    "id": "steward",
                    "name": "Ilse Voss",
                    "location": "observatory",
                    "player_known": True,
                    "goals": ["Keep the crew alive"],
                }
            ],
            "facts": [
                {
                    "id": "fact_signal",
                    "text": "The valley signal has been silent for three days.",
                    "visibility": "gm",
                },
                {
                    "id": "fact_snow",
                    "text": "The pass is closed by snow.",
                    "visibility": "player",
                },
            ],
        }
    )
    return payload


def test_empty_premise_retries_a_water_default() -> None:
    provider = SequenceProvider([seed_payload(), _mountain_payload()])
    generator = CampaignGenerator(provider, Settings(_env_file=None))  # type: ignore[arg-type]

    seed, usage = generator.generate(CampaignRequest())

    assert seed.title == "The High Observatory"
    assert len(provider.requests) == 2
    assert "water infrastructure" in provider.requests[1].user_input
    assert usage.input_tokens == 2


def test_explicit_water_premise_is_not_retried() -> None:
    provider = SequenceProvider([seed_payload()])
    generator = CampaignGenerator(provider, Settings(_env_file=None))  # type: ignore[arg-type]

    seed, usage = generator.generate(CampaignRequest(prompt="A harbor mystery."))

    assert seed.title
    assert len(provider.requests) == 1
    assert usage.input_tokens == 1


def test_character_hint_reaches_the_generator() -> None:
    provider = SequenceProvider([seed_payload()])
    generator = CampaignGenerator(provider, Settings(_env_file=None))  # type: ignore[arg-type]

    generator.generate(
        CampaignRequest(
            prompt="A harbor mystery.",
            character="A disgraced cartographer with more nerve than sense.",
        )
    )

    assert "disgraced cartographer" in provider.requests[0].user_input


def test_generation_retries_once_with_the_validation_error() -> None:
    provider = SequenceProvider(
        [
            {"title": "Broken", "opening_scene": "Rain."},
            seed_payload(),
        ]
    )
    generator = CampaignGenerator(provider, Settings(_env_file=None))  # type: ignore[arg-type]

    seed, usage = generator.generate(CampaignRequest(prompt="A harbor mystery."))

    assert seed.title
    assert len(provider.requests) == 2
    assert "failed validation" in provider.requests[1].user_input
    assert usage.input_tokens == 2
    assert usage.output_tokens == 2


def test_generation_reports_validation_failure_after_three_attempts() -> None:
    import pytest

    from atlas.agents.types import AgentError

    provider = SequenceProvider(
        [
            {"title": "Broken", "opening_scene": "Rain."},
            {"title": "Still broken", "opening_scene": "Rain."},
            {"title": "Broken again", "opening_scene": "Rain."},
        ]
    )
    generator = CampaignGenerator(provider, Settings(_env_file=None))  # type: ignore[arg-type]

    with pytest.raises(AgentError, match="failed validation after three attempts"):
        generator.generate(CampaignRequest(prompt="A harbor mystery."))
