from __future__ import annotations

from atlas.agents.loop import run_tool_loop
from atlas.agents.prompts import load_prompt
from atlas.agents.types import AgentReply, AgentRequest, Message, Provider
from atlas.config import Settings
from atlas.context import build_world_prompt
from atlas.state.schemas import CampaignState
from atlas.tools.context import ToolContext
from atlas.tools.registry import ToolRegistry


class WorldAgent:
    def __init__(self, provider: Provider, registry: ToolRegistry, settings: Settings) -> None:
        self.provider = provider
        self.registry = registry
        self.settings = settings

    def run(self, state: CampaignState, reason: str, ctx: ToolContext) -> AgentReply:
        request = AgentRequest(
            model=self.settings.world_model,
            instructions=load_prompt("world"),
            messages=[
                Message(
                    role="user",
                    content=build_world_prompt(
                        state,
                        reason,
                        char_budget=max(8_000, self.settings.context_char_budget // 2),
                    ),
                )
            ],
            tools=self.registry.schemas(),
            max_output_tokens=2_000,
        )
        return run_tool_loop(
            self.provider,
            self.registry,
            request,
            ctx,
            max_iterations=self.settings.max_tool_iterations,
        )
