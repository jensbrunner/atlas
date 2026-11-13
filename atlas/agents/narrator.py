from __future__ import annotations

from atlas.agents.loop import EventCallback, run_tool_loop
from atlas.agents.prompts import load_prompt
from atlas.agents.types import AgentReply, AgentRequest, Message, Provider
from atlas.config import Settings
from atlas.context import build_turn_prompt
from atlas.state.schemas import CampaignState
from atlas.tools.context import ToolContext
from atlas.tools.registry import ToolRegistry


class Narrator:
    def __init__(self, provider: Provider, registry: ToolRegistry, settings: Settings) -> None:
        self.provider = provider
        self.registry = registry
        self.settings = settings

    def play(
        self,
        state: CampaignState,
        action: str,
        ctx: ToolContext,
        *,
        on_event: EventCallback | None = None,
        narrative_lens: str = "",
    ) -> AgentReply:
        request = AgentRequest(
            model=self.settings.narrator_model,
            instructions=load_prompt("narrator"),
            messages=[
                Message(
                    role="user",
                    content=build_turn_prompt(
                        state,
                        action,
                        recent_turn_limit=self.settings.recent_turn_limit,
                        char_budget=self.settings.context_char_budget,
                        narrative_lens=narrative_lens,
                    ),
                )
            ],
            tools=self.registry.schemas(),
            max_output_tokens=self.settings.narrator_output_tokens,
        )
        return run_tool_loop(
            self.provider,
            self.registry,
            request,
            ctx,
            max_iterations=self.settings.max_tool_iterations,
            deadline_seconds=self.settings.turn_deadline_seconds,
            on_event=on_event,
        )

    def repair(
        self,
        state: CampaignState,
        action: str,
        draft: str,
        matched: str,
        ctx: ToolContext,
        *,
        on_event: EventCallback | None = None,
        narrative_lens: str = "",
    ) -> AgentReply:
        """Rewrite or reveal after the leak scan rejects a draft."""

        request = AgentRequest(
            model=self.settings.narrator_model,
            instructions=f"{load_prompt('narrator')}\n\n{load_prompt('repair')}",
            messages=[
                Message(
                    role="user",
                    content=build_turn_prompt(
                        state,
                        action,
                        recent_turn_limit=self.settings.recent_turn_limit,
                        char_budget=self.settings.context_char_budget,
                        narrative_lens=narrative_lens,
                    ),
                ),
                Message(role="assistant", content=draft),
                Message(
                    role="user",
                    content=(
                        "The draft above was rejected by the secret-leak check. "
                        f"The protected material it exposed was: {matched!r}. "
                        "Correct the turn now."
                    ),
                ),
            ],
            tools=self.registry.schemas(),
            max_output_tokens=self.settings.narrator_output_tokens,
        )
        return run_tool_loop(
            self.provider,
            self.registry,
            request,
            ctx,
            max_iterations=self.settings.max_tool_iterations,
            deadline_seconds=self.settings.turn_deadline_seconds,
            on_event=on_event,
        )
