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


def test_creative_brief_reaches_the_generator() -> None:
    provider = SequenceProvider([seed_payload()])
    generator = CampaignGenerator(provider, Settings(_env_file=None))  # type: ignore[arg-type]

    generator.generate(
        CampaignRequest(),
        creative_brief="- Setting seed: a mountain observatory",
    )

    assert "mountain observatory" in provider.requests[0].user_input


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


def test_generation_reports_validation_failure_after_two_attempts() -> None:
    import pytest

    from atlas.agents.types import AgentError

    provider = SequenceProvider(
        [
            {"title": "Broken", "opening_scene": "Rain."},
            {"title": "Still broken", "opening_scene": "Rain."},
        ]
    )
    generator = CampaignGenerator(provider, Settings(_env_file=None))  # type: ignore[arg-type]

    with pytest.raises(AgentError, match="failed validation after two attempts"):
        generator.generate(CampaignRequest(prompt="A harbor mystery."))
