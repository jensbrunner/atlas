from __future__ import annotations

import json
from typing import Any, cast

from atlas.agents.types import (
    AgentError,
    AgentReply,
    AgentRequest,
    Message,
    Provider,
    StructuredRequest,
    ToolCall,
)
from atlas.state.schemas import Usage


class OpenAIProvider:
    """Adapter for the OpenAI Responses API.

    The client is created lazily so importing ATLAS never requires a key or a
    network connection.
    """

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 90.0,
        client: Any | None = None,
        input_usd_per_million: float = 0.0,
        output_usd_per_million: float = 0.0,
    ) -> None:
        self._input_rate = input_usd_per_million
        self._output_rate = output_usd_per_million
        if client is not None:
            self._client = client
            return
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise AgentError("the openai package is not installed") from exc
        self._client = OpenAI(api_key=api_key, timeout=timeout, max_retries=0)

    # -- narrator/tool loop -------------------------------------------

    def complete(self, request: AgentRequest) -> AgentReply:
        response = self._client.responses.create(
            model=request.model,
            instructions=request.instructions,
            input=cast(Any, _input_items(request.messages)),
            tools=cast(Any, request.tools),
            max_output_tokens=request.max_output_tokens,
        )
        text = _response_text(response)
        calls: list[ToolCall] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "function_call":
                continue
            raw = getattr(item, "arguments", "") or "{}"
            try:
                arguments = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AgentError(f"model returned invalid JSON for {item.name}") from exc
            if not isinstance(arguments, dict):
                raise AgentError(f"model returned non-object arguments for {item.name}")
            calls.append(
                ToolCall(
                    id=str(getattr(item, "call_id", "") or getattr(item, "id", "")),
                    name=str(item.name),
                    arguments=arguments,
                )
            )
        return AgentReply(
            text=text,
            tool_calls=calls,
            usage=_usage(
                response,
                input_rate=self._input_rate,
                output_rate=self._output_rate,
            ),
        )

    # -- structured generation ---------------------------------------

    def generate_structured(self, request: StructuredRequest) -> tuple[dict[str, Any], Usage]:
        response = self._client.responses.create(
            model=request.model,
            instructions=request.instructions,
            input=cast(Any, [{"role": "user", "content": request.user_input}]),
            tools=cast(
                Any,
                [
                    {
                        "type": "function",
                        "name": request.tool_name,
                        "description": request.tool_description,
                        "parameters": request.parameters,
                    }
                ],
            ),
            tool_choice=cast(Any, {"type": "function", "name": request.tool_name}),
            max_output_tokens=request.max_output_tokens,
        )
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "function_call":
                continue
            if getattr(item, "name", None) != request.tool_name:
                continue
            raw = getattr(item, "arguments", "") or "{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AgentError("model returned invalid structured JSON") from exc
            if not isinstance(payload, dict):
                raise AgentError("model returned a non-object structured payload")
            return payload, _usage(
                response,
                input_rate=self._input_rate,
                output_rate=self._output_rate,
            )
        raise AgentError(f"model did not call required tool {request.tool_name}")


def _input_items(messages: list[Message]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            if not message.tool_call_id:
                raise AgentError("tool message is missing tool_call_id")
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                }
            )
            continue
        if message.role == "assistant":
            if message.content.strip():
                items.append({"role": "assistant", "content": message.content})
            for call in message.tool_calls:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    }
                )
            continue
        items.append({"role": message.role, "content": message.content})
    return items


def _response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                parts.append(str(value))
    return "\n".join(parts)


def _usage(
    response: Any,
    *,
    input_rate: float = 0.0,
    output_rate: float = 0.0,
) -> Usage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return Usage()
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    estimated = input_tokens / 1_000_000 * input_rate + output_tokens / 1_000_000 * output_rate
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_usd=round(estimated, 6),
    )


def build_provider(
    *,
    provider: str,
    api_key: str | None,
    timeout: float = 90.0,
    input_usd_per_million: float = 0.0,
    output_usd_per_million: float = 0.0,
) -> Provider:
    if provider == "openai":
        if not api_key:
            raise ValueError("an OpenAI API key is required for ATLAS_PROVIDER=openai")
        return OpenAIProvider(
            api_key,
            timeout=timeout,
            input_usd_per_million=input_usd_per_million,
            output_usd_per_million=output_usd_per_million,
        )
    from atlas.agents.fake import FakeProvider

    return FakeProvider()
