from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from atlas.state.schemas import Usage

MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    role: MessageRole
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class AgentRequest:
    model: str
    instructions: str
    messages: list[Message]
    tools: list[dict[str, Any]] = field(default_factory=list)
    max_output_tokens: int = 4_000


@dataclass
class AgentReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


@dataclass
class StructuredRequest:
    model: str
    instructions: str
    user_input: str
    tool_name: str
    tool_description: str
    parameters: dict[str, Any]
    max_output_tokens: int = 6_000


class Provider(Protocol):
    def complete(self, request: AgentRequest) -> AgentReply: ...

    def generate_structured(self, request: StructuredRequest) -> tuple[dict[str, Any], Usage]: ...


class AgentError(Exception):
    """The model failed to produce a usable response."""


def add_usage(left: Usage, right: Usage) -> Usage:
    return Usage(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        estimated_usd=round(left.estimated_usd + right.estimated_usd, 6),
    )
