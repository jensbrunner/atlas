from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from atlas.agents.prompts import load_prompt
from atlas.agents.types import AgentError, Provider, StructuredRequest, add_usage
from atlas.config import Settings
from atlas.state.schemas import CampaignSeed, Usage


@dataclass
class CampaignRequest:
    title: str = ""
    prompt: str = ""
    genre: str = ""
    tone: str = ""
    character: str = ""


def _obj(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_ATTRIBUTES = _obj(
    {
        "might": {"type": "integer", "minimum": -2, "maximum": 6},
        "agility": {"type": "integer", "minimum": -2, "maximum": 6},
        "insight": {"type": "integer", "minimum": -2, "maximum": 6},
        "presence": {"type": "integer", "minimum": -2, "maximum": 6},
    },
    ["might", "agility", "insight", "presence"],
)

_ITEM = _obj(
    {
        "name": {"type": "string"},
        "quantity": {"type": "integer", "minimum": 1},
        "tags": {"type": "array", "items": {"type": "string"}},
        "description": {"type": "string"},
    },
    ["name", "quantity"],
)

_CHARACTER = _obj(
    {
        "name": {"type": "string"},
        "concept": {"type": "string"},
        "attributes": _ATTRIBUTES,
        "skills": {"type": "object", "additionalProperties": {"type": "integer"}},
        "health_max": {"type": "integer", "minimum": 1, "maximum": 20},
        "stress_max": {"type": "integer", "minimum": 1, "maximum": 20},
        "supplies": {"type": "integer", "minimum": 0},
        "currency": {"type": "integer", "minimum": 0},
        "conditions": {"type": "array", "items": {"type": "string"}},
        "inventory": {"type": "array", "items": _ITEM},
        "appearance": {"type": "string"},
        "background": {"type": "string"},
    },
    ["name", "attributes"],
)

_LOCATION = _obj(
    {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "player_known": {"type": "boolean"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    ["id", "name"],
)

_FACTION = _obj(
    {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "goal": {"type": "string"},
        "stance": {"type": "string"},
        "resources": {"type": "object", "additionalProperties": {"type": "integer"}},
        "player_known": {"type": "boolean"},
    },
    ["id", "name"],
)

_CLOCK = _obj(
    {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "segments": {"type": "integer", "minimum": 1, "maximum": 20},
        "filled": {"type": "integer", "minimum": 0, "maximum": 20},
        "trigger": {"type": "string"},
        "visibility": {"type": "string", "enum": ["gm", "player"]},
    },
    ["id", "name", "segments"],
)

_FACT = _obj(
    {
        "id": {
            "type": "string",
            "description": "Stable lowercase id with underscores, e.g. fact_missing_manifest.",
        },
        "text": {"type": "string"},
        "visibility": {"type": "string", "enum": ["gm", "player"]},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    ["text", "visibility"],
)

_NPC = _obj(
    {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "location": {"type": "string"},
        "player_known": {"type": "boolean"},
        "attitude": {"type": "string"},
        "attributes": _ATTRIBUTES,
        "skills": {"type": "object", "additionalProperties": {"type": "integer"}},
        "health_max": {"type": "integer", "minimum": 1, "maximum": 20},
        "goals": {"type": "array", "items": {"type": "string"}},
        "plans": {
            "type": "array",
            "items": {
                "type": "string",
                "description": "A concrete step the NPC is taking now to pursue a goal.",
            },
        },
        "knows": {
            "type": "array",
            "items": {
                "type": "string",
                "description": "A fact id from the facts array. Never put prose here.",
            },
        },
        "appearance": {"type": "string"},
        "secret": {"type": "string"},
    },
    ["id", "name"],
)

CAMPAIGN_PARAMETERS = _obj(
    {
        "title": {"type": "string"},
        "genre": {"type": "string"},
        "tone": {"type": "string"},
        "premise": {"type": "string"},
        "notes": {"type": "string"},
        "opening_scene": {"type": "string"},
        "start_minute": {
            "type": "integer",
            "minimum": 0,
            "maximum": 1439,
            "description": "Minutes after midnight for the opening scene, e.g. 1080 = 18:00.",
        },
        "current_location": {"type": "string"},
        "character": _CHARACTER,
        "locations": {"type": "array", "items": _LOCATION},
        "factions": {"type": "array", "items": _FACTION},
        "clocks": {"type": "array", "items": _CLOCK},
        "facts": {"type": "array", "items": _FACT},
        "npcs": {"type": "array", "items": _NPC},
    },
    ["title", "opening_scene", "current_location", "character", "locations"],
)


def _validation_summary(exc: ValidationError) -> str:
    lines = []
    for error in exc.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in error.get("loc", ())) or "campaign"
        lines.append(f"- {location}: {error.get('msg', 'invalid value')}")
    return "\n".join(lines)


class CampaignGenerator:
    def __init__(self, provider: Provider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings

    def generate(
        self,
        request: CampaignRequest,
    ) -> tuple[CampaignSeed, Usage]:
        lines = [
            f"Title hint: {request.title or 'none'}",
            f"Prompt: {request.prompt or 'Invent a fresh campaign.'}",
            f"Genre: {request.genre or 'your choice'}",
            f"Tone: {request.tone or 'your choice'}",
            f"Player character hint: {request.character or 'your choice'}",
        ]
        lines.append("Create the campaign now. Fill every field that matters.")
        user_input = "\n".join(lines)
        total_usage = Usage()
        last_error: ValidationError | None = None
        retry_issue: str | None = None
        for _ in range(2):
            prompt = user_input
            corrections: list[str] = []
            if retry_issue is not None:
                corrections.append(retry_issue)
            if last_error is not None:
                corrections.append(
                    "Your previous submission failed validation. Fix exactly these "
                    f"problems and resubmit the complete campaign:\n"
                    f"{_validation_summary(last_error)}"
                )
            if corrections:
                prompt = f"{user_input}\n\n" + "\n\n".join(corrections)

            try:
                payload, usage = self.provider.generate_structured(
                    StructuredRequest(
                        model=self.settings.campaign_model,
                        instructions=load_prompt("campaign"),
                        user_input=prompt,
                        tool_name="submit_campaign",
                        tool_description="Submit a complete, ready-to-play campaign seed.",
                        parameters=CAMPAIGN_PARAMETERS,
                        max_output_tokens=10_000,
                    )
                )
            except AgentError as exc:
                if "invalid structured JSON" not in str(exc):
                    raise
                retry_issue = (
                    "Your previous response was incomplete or invalid JSON. Return a "
                    "complete campaign payload. Keep prose and lists compact so every "
                    "required field is fully closed."
                )
                continue
            total_usage = add_usage(total_usage, usage)
            try:
                seed = CampaignSeed.model_validate(payload)
            except ValidationError as exc:
                last_error = exc
                continue

            return seed, total_usage

        if last_error is not None:
            summary = _validation_summary(last_error)
            raise AgentError(
                "campaign generation failed validation after two attempts:\n" + summary
            )
        raise AgentError(
            "campaign generation returned incomplete structured output after two attempts"
        )
