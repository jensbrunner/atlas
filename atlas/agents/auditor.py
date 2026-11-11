from __future__ import annotations

from typing import Any

from atlas.agents.prompts import load_prompt
from atlas.agents.types import Provider, StructuredRequest
from atlas.config import Settings
from atlas.context import build_audit_prompt
from atlas.state.schemas import CampaignState, Usage

AUDIT_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "summary": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["severity", "summary", "evidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


class Auditor:
    def __init__(self, provider: Provider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings

    def audit(self, state: CampaignState) -> tuple[list[dict[str, str]], Usage]:
        payload, usage = self.provider.generate_structured(
            StructuredRequest(
                model=self.settings.auditor_model,
                instructions=load_prompt("auditor"),
                user_input=build_audit_prompt(state),
                tool_name="submit_audit",
                tool_description="Submit continuity findings for this campaign.",
                parameters=AUDIT_PARAMETERS,
                max_output_tokens=2_000,
            )
        )
        raw = payload.get("findings", [])
        if not isinstance(raw, list):
            raise ValueError("audit findings must be a list")
        findings: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            findings.append(
                {
                    "severity": str(item.get("severity", "low")),
                    "summary": str(item.get("summary", "")),
                    "evidence": str(item.get("evidence", "")),
                }
            )
        return findings, usage
