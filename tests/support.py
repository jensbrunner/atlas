from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from atlas.agents.fake import FakeProvider, default_seed
from atlas.agents.types import AgentError, AgentReply, AgentRequest, ToolCall
from atlas.config import Settings
from atlas.game import CampaignService


def seed_payload(**overrides: Any) -> dict[str, Any]:
    payload = default_seed("A rain-soaked harbor town with a missing shipment.")
    payload.update(overrides)
    return payload


def fake_provider(
    *,
    replies: list[AgentReply] | None = None,
    seed: dict[str, Any] | None = None,
    audit_findings: list[dict[str, str]] | None = None,
) -> FakeProvider:
    return FakeProvider(
        replies=replies,
        campaign_seed=seed if seed is not None else seed_payload(),
        audit_findings=audit_findings,
    )


def make_service(
    tmp_path: Path,
    provider: FakeProvider | None = None,
    *,
    rng_seed: int = 7,
) -> CampaignService:
    settings = Settings(data_dir=tmp_path / "campaigns", provider="fake")
    return CampaignService(
        settings,
        provider=provider or fake_provider(),
        rng_factory=lambda: random.Random(rng_seed),
    )


def tool(tool_name: str, call_id: str, **arguments: Any) -> ToolCall:
    return ToolCall(id=call_id, name=tool_name, arguments=arguments)


class FailingProvider(FakeProvider):
    def complete(self, request: AgentRequest) -> AgentReply:
        raise AgentError("simulated provider failure")
