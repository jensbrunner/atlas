"""Character templates, attributes, training, and challenge math.

M2 introduces the four attributes from VISION §7: Might, Agility, Insight, and
Presence. Player characters are built from one of a small set of viable
templates; NPCs use the same challenge math through their entity static data.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from atlas.domain.models import ResourceName, StrictModel

ATTRIBUTE_MIN = -1
ATTRIBUTE_MAX = 2
TRAINING_MIN = 0
TRAINING_MAX = 2
DIFFICULTY_MIN = 0
DIFFICULTY_MAX = 3


class Attribute(StrEnum):
    MIGHT = "might"
    AGILITY = "agility"
    INSIGHT = "insight"
    PRESENCE = "presence"


class Skill(StrEnum):
    NEGOTIATION = "negotiation"
    ENGINEERING = "engineering"
    CONFRONTATION = "confrontation"
    SURVIVAL = "survival"


class Attributes(StrictModel):
    might: int = Field(default=0, ge=ATTRIBUTE_MIN, le=ATTRIBUTE_MAX)
    agility: int = Field(default=0, ge=ATTRIBUTE_MIN, le=ATTRIBUTE_MAX)
    insight: int = Field(default=0, ge=ATTRIBUTE_MIN, le=ATTRIBUTE_MAX)
    presence: int = Field(default=0, ge=ATTRIBUTE_MIN, le=ATTRIBUTE_MAX)

    def value(self, attribute: Attribute) -> int:
        return int(getattr(self, attribute.value))


class Training(StrictModel):
    negotiation: int = Field(default=0, ge=TRAINING_MIN, le=TRAINING_MAX)
    engineering: int = Field(default=0, ge=TRAINING_MIN, le=TRAINING_MAX)
    confrontation: int = Field(default=0, ge=TRAINING_MIN, le=TRAINING_MAX)
    survival: int = Field(default=0, ge=TRAINING_MIN, le=TRAINING_MAX)

    def value(self, skill: Skill) -> int:
        return int(getattr(self, skill.value))


class CharacterTemplate(StrictModel):
    """A viable starting character with no long creation workflow."""

    slug: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    display_name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=400)
    attributes: Attributes
    training: Training
    health: int = Field(ge=1, le=10)
    stress: int = Field(default=0, ge=0, le=10)
    supplies: int = Field(default=0, ge=0, le=99)
    currency: int = Field(default=0, ge=0, le=9_999)
    equipment: list[str] = Field(default_factory=list)
    abilities: list[str] = Field(default_factory=list)

    def static_payload(self) -> dict[str, Any]:
        return {
            "template": self.slug,
            "description": self.description,
            "attributes": self.attributes.model_dump(mode="json"),
            "training": self.training.model_dump(mode="json"),
            "equipment": list(self.equipment),
            "abilities": list(self.abilities),
            "resource_bounds": {
                "health": {"min": 0, "max": 10},
                "stress": {"min": 0, "max": 10},
                "supplies": {"min": 0, "max": 99},
                "currency": {"min": 0, "max": 9_999},
            },
        }

    def state_payload(self, location_id: str) -> dict[str, Any]:
        return {
            "location_id": location_id,
            "health": self.health,
            "stress": self.stress,
            ResourceName.SUPPLIES.value: self.supplies,
            ResourceName.CURRENCY.value: self.currency,
            "inventory": {},
        }


CHARACTER_TEMPLATES: dict[str, CharacterTemplate] = {
    "river_fixer": CharacterTemplate(
        slug="river_fixer",
        display_name="Rowan the River Fixer",
        description="A travelling fixer with a practical streak and a good ear.",
        attributes=Attributes(might=1, agility=1, insight=2, presence=0),
        training=Training(negotiation=0, engineering=1, confrontation=0, survival=1),
        health=7,
        stress=1,
        supplies=2,
        currency=12,
        equipment=["work knife", "rope", "writing kit"],
        abilities=["Field repair", "Read the room"],
    ),
    "town_advocate": CharacterTemplate(
        slug="town_advocate",
        display_name="Rowan the Town Advocate",
        description="A patient negotiator who knows when a promise is worth more than coin.",
        attributes=Attributes(might=0, agility=1, insight=1, presence=2),
        training=Training(negotiation=2, engineering=0, confrontation=0, survival=1),
        health=6,
        stress=2,
        supplies=3,
        currency=18,
        equipment=["fine cloak", "seal of office", "ledger"],
        abilities=["Silver tongue", "Find the common ground"],
    ),
    "stone_warden": CharacterTemplate(
        slug="stone_warden",
        display_name="Rowan the Stone Warden",
        description="A broad-shouldered labourer who has hauled stone for half the valley.",
        attributes=Attributes(might=2, agility=1, insight=0, presence=1),
        training=Training(negotiation=0, engineering=1, confrontation=1, survival=2),
        health=8,
        stress=0,
        supplies=4,
        currency=8,
        equipment=["sledge", "crowbar", "heavy gloves"],
        abilities=["Shoulder the load", "Stand firm"],
    ),
}

DEFAULT_TEMPLATE_SLUG = "river_fixer"


def get_character_template(slug: str) -> CharacterTemplate:
    try:
        return CHARACTER_TEMPLATES[slug]
    except KeyError as exc:
        raise ValueError(f"unknown character template {slug!r}") from exc


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def attribute_value(static: dict[str, Any], attribute: Attribute) -> int:
    raw = static.get("attributes", {})
    value = raw.get(attribute.value, 0) if isinstance(raw, dict) else 0
    return _clamp(int(value), ATTRIBUTE_MIN, ATTRIBUTE_MAX)


def training_value(static: dict[str, Any], skill: Skill) -> int:
    raw = static.get("training", {})
    value = raw.get(skill.value, 0) if isinstance(raw, dict) else 0
    return _clamp(int(value), TRAINING_MIN, TRAINING_MAX)


def challenge_modifier(static: dict[str, Any], attribute: Attribute, skill: Skill) -> int:
    return attribute_value(static, attribute) + training_value(static, skill)


def clamp_difficulty(value: int) -> int:
    return _clamp(value, DIFFICULTY_MIN, DIFFICULTY_MAX)
