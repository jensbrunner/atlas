from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from atlas.agents.fake import FakeProvider
from atlas.agents.providers import OpenAIProvider, build_provider
from atlas.agents.types import (
    AgentError,
    AgentRequest,
    Message,
    StructuredRequest,
    ToolCall,
)


class StubResponses:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


class StubClient:
    def __init__(self, response: Any) -> None:
        self.responses = StubResponses(response)


def _provider(response: Any) -> tuple[OpenAIProvider, StubClient]:
    client = StubClient(response)
    return OpenAIProvider("sk-test", client=client), client


def _request() -> AgentRequest:
    return AgentRequest(
        model="gpt-6-luna",
        instructions="You are the narrator.",
        messages=[Message(role="user", content="look around")],
        tools=[{"type": "function", "name": "roll", "parameters": {"type": "object"}}],
        max_output_tokens=123,
    )


def test_complete_maps_text_tools_and_usage() -> None:
    response = SimpleNamespace(
        output_text="You see the harbor.",
        output=[
            SimpleNamespace(
                type="function_call",
                name="roll",
                arguments='{"label": "climb", "attribute": "agility", "difficulty": 8}',
                call_id="call_1",
            )
        ],
        usage=SimpleNamespace(input_tokens=12, output_tokens=8),
    )
    provider, client = _provider(response)
    reply = provider.complete(_request())

    assert reply.text == "You see the harbor."
    assert reply.tool_calls == [
        ToolCall(
            id="call_1",
            name="roll",
            arguments={"label": "climb", "attribute": "agility", "difficulty": 8},
        )
    ]
    assert reply.usage.input_tokens == 12
    assert reply.usage.output_tokens == 8
    assert client.responses.kwargs is not None
    kwargs = client.responses.kwargs
    assert kwargs["model"] == "gpt-6-luna"
    assert kwargs["instructions"] == "You are the narrator."
    assert kwargs["max_output_tokens"] == 123
    assert kwargs["input"] == [{"role": "user", "content": "look around"}]


def test_tool_results_are_sent_as_function_call_output() -> None:
    response = SimpleNamespace(output_text="Done.", output=[], usage=None)
    provider, client = _provider(response)
    request = _request()
    request.messages = [
        Message(role="user", content="look around"),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="call_1", name="roll", arguments={"label": "x"})],
        ),
        Message(role="tool", content="success", tool_call_id="call_1", name="roll"),
    ]

    provider.complete(request)

    assert client.responses.kwargs is not None
    items = client.responses.kwargs["input"]
    assert items[1] == {
        "type": "function_call",
        "call_id": "call_1",
        "name": "roll",
        "arguments": '{"label": "x"}',
    }
    assert items[2] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "success",
    }


def test_structured_generation_forces_the_named_tool() -> None:
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="submit_campaign",
                arguments='{"title": "The Quiet Harbor"}',
            )
        ],
        usage=SimpleNamespace(input_tokens=5, output_tokens=3),
    )
    provider, client = _provider(response)
    payload, usage = provider.generate_structured(
        StructuredRequest(
            model="gpt-6-luna",
            instructions="Invent a campaign.",
            user_input="A harbor mystery.",
            tool_name="submit_campaign",
            tool_description="Submit a campaign.",
            parameters={"type": "object", "properties": {}},
        )
    )

    assert payload == {"title": "The Quiet Harbor"}
    assert usage.output_tokens == 3
    assert client.responses.kwargs is not None
    assert client.responses.kwargs["tool_choice"] == {
        "type": "function",
        "name": "submit_campaign",
    }


def test_structured_generation_requires_the_tool_call() -> None:
    response = SimpleNamespace(output_text="I forgot the tool.", output=[], usage=None)
    provider, _ = _provider(response)

    with pytest.raises(AgentError, match="did not call required tool"):
        provider.generate_structured(
            StructuredRequest(
                model="gpt-6-luna",
                instructions="Invent a campaign.",
                user_input="A harbor mystery.",
                tool_name="submit_campaign",
                tool_description="Submit a campaign.",
                parameters={"type": "object"},
            )
        )


def test_invalid_tool_json_is_reported() -> None:
    response = SimpleNamespace(
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                name="roll",
                arguments="{not json",
                call_id="call_1",
            )
        ],
        usage=None,
    )
    provider, _ = _provider(response)

    with pytest.raises(AgentError, match="invalid JSON"):
        provider.complete(_request())


def test_provider_factory_requires_a_key_only_for_openai() -> None:
    with pytest.raises(ValueError, match="API key is required"):
        build_provider(provider="openai", api_key=None)
    assert isinstance(build_provider(provider="fake", api_key=None), FakeProvider)


def test_usage_uses_builtin_price_for_known_models() -> None:
    response = SimpleNamespace(
        output_text="Done.",
        output=[],
        usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=500_000),
    )
    client = StubClient(response)
    provider = OpenAIProvider(
        "sk-test",
        client=client,
        input_usd_per_million=2.0,
        output_usd_per_million=4.0,
    )

    reply = provider.complete(_request())

    assert reply.usage.input_tokens == 1_000_000
    assert reply.usage.output_tokens == 500_000
    assert reply.usage.estimated_usd == 0.35


def test_usage_uses_fallback_rates_for_unknown_models() -> None:
    response = SimpleNamespace(
        output_text="Done.",
        output=[],
        usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=500_000),
    )
    client = StubClient(response)
    provider = OpenAIProvider(
        "sk-test",
        client=client,
        input_usd_per_million=2.0,
        output_usd_per_million=4.0,
    )
    request = _request()
    request.model = "custom-house-model"

    reply = provider.complete(request)

    assert reply.usage.estimated_usd == 4.0
