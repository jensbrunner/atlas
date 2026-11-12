from __future__ import annotations

import json
import time
from dataclasses import replace

from atlas.agents.types import AgentError, AgentReply, AgentRequest, Message, Provider, add_usage
from atlas.state.schemas import Usage
from atlas.tools.context import ToolContext
from atlas.tools.registry import ToolRegistry

_DESCRIPTIVE_ARGUMENTS = {"reason"}


def _call_key(name: str, arguments: dict[str, object]) -> tuple[str, str]:
    """A stable identity for one tool effect within a turn.

    Purely descriptive fields such as a clock's `reason` are ignored so a model
    cannot apply the same mechanical change twice by rewording it.
    """

    normalized = {
        key: value for key, value in arguments.items() if key not in _DESCRIPTIVE_ARGUMENTS
    }
    return name, json.dumps(normalized, sort_keys=True, default=str)


def run_tool_loop(
    provider: Provider,
    registry: ToolRegistry,
    request: AgentRequest,
    ctx: ToolContext,
    *,
    max_iterations: int,
    deadline_seconds: float | None = None,
) -> AgentReply:
    messages: list[Message] = list(request.messages)
    usage = Usage()
    last_text = ""
    started = time.monotonic()
    applied: set[tuple[str, str]] = set()

    for _ in range(max_iterations):
        if deadline_seconds is not None and time.monotonic() - started > deadline_seconds:
            raise AgentError(
                f"turn exceeded its {deadline_seconds:.0f}s deadline; no changes were saved"
            )
        reply = provider.complete(replace(request, messages=messages))
        usage = add_usage(usage, reply.usage)
        if reply.text.strip():
            last_text = reply.text.strip()
        if not reply.tool_calls:
            return AgentReply(text=last_text, usage=usage)

        messages.append(Message(role="assistant", content=reply.text, tool_calls=reply.tool_calls))
        for call in reply.tool_calls:
            key = _call_key(call.name, call.arguments)
            if key in applied:
                result = (
                    "ERROR: duplicate tool call ignored; this change was already "
                    "applied this turn. Continue with any remaining changes and narrate."
                )
            else:
                result = registry.execute(ctx, call.name, call.arguments)
                if not result.startswith("ERROR:"):
                    applied.add(key)
            messages.append(
                Message(
                    role="tool",
                    content=result,
                    tool_call_id=call.id,
                    name=call.name,
                )
            )

    raise AgentError(f"tool loop exceeded {max_iterations} iterations")
