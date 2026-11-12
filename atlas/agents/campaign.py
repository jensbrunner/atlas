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


class CampaignGenerator:
    def __init__(self, provider: Provider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings

    def generate(
        self,
        request: CampaignRequest,
        *,
        avoid_names: list[str] | None = None,
    ) -> tuple[CampaignSeed, Usage]:
        lines = [
            f"Title hint: {request.title or 'none'}",
            f"Prompt: {request.prompt or 'Invent a fresh campaign.'}",
            f"Genre: {request.genre or 'your choice'}",
            f"Tone: {request.tone or 'your choice'}",
        ]
        names = sorted({name.strip() for name in (avoid_names or []) if name.strip()})
        if names:
            lines.append(
                "Do not reuse these names from earlier campaigns: " + ", ".join(names[:80])
            )
        lines.append("Create the campaign now. Fill every field that matters.")
        user_input = "\n".join(lines)
        total_usage = Usage()
        last_error: ValidationError | None = None
        for attempt in range(2):
            prompt = user_input
            if attempt and last_error is not None:
                prompt = (
                    f"{user_input}\n\n"
                    "Your previous submission failed validation. Fix exactly these "
                    f"problems and resubmit the complete campaign:\n{last_error}"
                )
            payload, usage = self.provider.generate_structured(
                StructuredRequest(
                    model=self.settings.campaign_model,
                    instructions=load_prompt("campaign"),
                    user_input=prompt,
                    tool_name="submit_campaign",
                    tool_description="Submit a complete, ready-to-play campaign seed.",
                    parameters=CAMPAIGN_PARAMETERS,
                    max_output_tokens=6_000,
                )
            )
            total_usage = add_usage(total_usage, usage)
            try:
                return CampaignSeed.model_validate(payload), total_usage
            except ValidationError as exc:
                last_error = exc

        raise AgentError(f"campaign generation failed validation after two attempts: {last_error}")
