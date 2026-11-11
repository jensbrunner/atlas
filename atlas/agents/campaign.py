from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlas.agents.prompts import load_prompt
from atlas.agents.types import Provider, StructuredRequest
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
        "id": {"type": "string"},
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
        "knows": {"type": "array", "items": {"type": "string"}},
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

    def generate(self, request: CampaignRequest) -> tuple[CampaignSeed, Usage]:
        user_input = "\n".join(
            [
                f"Title hint: {request.title or 'none'}",
                f"Prompt: {request.prompt or 'Invent a fresh campaign.'}",
                f"Genre: {request.genre or 'your choice'}",
                f"Tone: {request.tone or 'your choice'}",
                "Create the campaign now. Fill every field that matters.",
            ]
        )
        payload, usage = self.provider.generate_structured(
            StructuredRequest(
                model=self.settings.campaign_model,
                instructions=load_prompt("campaign"),
                user_input=user_input,
                tool_name="submit_campaign",
                tool_description="Submit a complete, ready-to-play campaign seed.",
                parameters=CAMPAIGN_PARAMETERS,
                max_output_tokens=6_000,
            )
        )
        return CampaignSeed.model_validate(payload), usage
