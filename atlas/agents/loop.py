from __future__ import annotations

from dataclasses import replace

from atlas.agents.types import AgentError, AgentReply, AgentRequest, Message, Provider, add_usage
from atlas.state.schemas import Usage
from atlas.tools.context import ToolContext
from atlas.tools.registry import ToolRegistry


def run_tool_loop(
    provider: Provider,
    registry: ToolRegistry,
    request: AgentRequest,
    ctx: ToolContext,
    *,
    max_iterations: int,
) -> AgentReply:
    messages: list[Message] = list(request.messages)
    usage = Usage()
    last_text = ""

    for _ in range(max_iterations):
        reply = provider.complete(replace(request, messages=messages))
        usage = add_usage(usage, reply.usage)
        if reply.text.strip():
            last_text = reply.text.strip()
        if not reply.tool_calls:
            return AgentReply(text=last_text, usage=usage)

        messages.append(Message(role="assistant", content=reply.text, tool_calls=reply.tool_calls))
        for call in reply.tool_calls:
            result = registry.execute(ctx, call.name, call.arguments)
            messages.append(
                Message(
                    role="tool",
                    content=result,
                    tool_call_id=call.id,
                    name=call.name,
                )
            )

    raise AgentError(f"tool loop exceeded {max_iterations} iterations")
