from __future__ import annotations

from typing import Literal

import pytest
from atlas.models.fake import FakeModelGateway
from atlas.models.interfaces import ModelGatewayError
from pydantic import BaseModel, ConfigDict


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["move", "speak"]
    target: str


@pytest.mark.asyncio
async def test_text_generation_is_deterministic() -> None:
    gateway = FakeModelGateway()
    messages = [{"role": "user", "content": "hello"}]
    first = await gateway.generate_text("narrator", messages)
    second = await gateway.generate_text("narrator", messages)
    assert first.content == second.content
    assert first.provider == "fake"
    assert first.estimated_cost_usd == 0.0


@pytest.mark.asyncio
async def test_scripted_text_is_returned_in_order() -> None:
    gateway = FakeModelGateway(text_responses={"narrator": ["one", "two"]})
    assert (await gateway.generate_text("narrator", [])).content == "one"
    assert (await gateway.generate_text("narrator", [])).content == "two"


@pytest.mark.asyncio
async def test_structured_output_is_validated() -> None:
    gateway = FakeModelGateway(
        structured_responses={"intent_parser": [{"kind": "speak", "target": "giant"}]}
    )
    result = await gateway.generate_structured("intent_parser", [], Proposal)
    assert result.value == Proposal(kind="speak", target="giant")


@pytest.mark.asyncio
async def test_structured_output_rejects_extra_fields() -> None:
    gateway = FakeModelGateway(
        structured_responses={
            "intent_parser": [{"kind": "speak", "target": "giant", "injected": True}]
        }
    )
    with pytest.raises(ModelGatewayError, match="failed schema validation"):
        await gateway.generate_structured("intent_parser", [], Proposal)


@pytest.mark.asyncio
async def test_missing_structured_response_is_an_explicit_error() -> None:
    gateway = FakeModelGateway()
    with pytest.raises(ModelGatewayError, match="no scripted structured response"):
        await gateway.generate_structured("intent_parser", [], Proposal)
