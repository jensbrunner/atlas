from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from atlas.ids import slugify

Visibility = Literal["gm", "player"]
TurnKind = Literal["opening", "player", "world"]


def _normalize_fact_text(text: str) -> str:
    cleaned = text.casefold().replace("*", "").replace("_", " ")
    return " ".join(cleaned.split()).strip(" .,:;!?\"'")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DraftModel(BaseModel):
    """Tolerant base for model-generated drafts.

    The model may volunteer extra fields. Unknown draft fields are ignored
    rather than failing an otherwise good campaign; canonical state stays strict.
    """

    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class Attributes(StrictModel):
    might: int = Field(default=0, ge=-2, le=6)
    agility: int = Field(default=0, ge=-2, le=6)
    insight: int = Field(default=0, ge=-2, le=6)
    presence: int = Field(default=0, ge=-2, le=6)


class Track(StrictModel):
    current: int = Field(ge=0)
    max: int = Field(ge=1)

    @model_validator(mode="after")
    def _bounded(self) -> Track:
        if self.current > self.max:
            self.current = self.max
        return self


class InventoryItem(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: int = Field(default=1, ge=0, le=10_000)
    tags: list[str] = Field(default_factory=list)
    description: str = ""


class Character(StrictModel):
    id: str
    name: str = Field(min_length=1, max_length=120)
    concept: str = ""
    attributes: Attributes = Field(default_factory=Attributes)
    skills: dict[str, int] = Field(default_factory=dict)
    health: Track = Field(default_factory=lambda: Track(current=7, max=7))
    stress: Track = Field(default_factory=lambda: Track(current=1, max=10))
    supplies: int = Field(default=0, ge=0)
    currency: int = Field(default=0, ge=0)
    conditions: list[str] = Field(default_factory=list)
    inventory: dict[str, InventoryItem] = Field(default_factory=dict)


class Location(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    player_known: bool = True
    tags: list[str] = Field(default_factory=list)


class Faction(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    goal: str = ""
    stance: str = "neutral"
    resources: dict[str, int] = Field(default_factory=dict)
    player_known: bool = True


class Clock(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    segments: int = Field(default=4, ge=1, le=20)
    filled: int = Field(default=0, ge=0, le=20)
    trigger: str = ""
    visibility: Visibility = "player"

    @model_validator(mode="after")
    def _filled_within(self) -> Clock:
        if self.filled > self.segments:
            raise ValueError("clock filled cannot exceed segments")
        return self


class Fact(StrictModel):
    id: str
    text: str = Field(min_length=1, max_length=2_000)
    visibility: Visibility = "gm"
    tags: list[str] = Field(default_factory=list)
    revealed_at_turn: int | None = None


class NPC(StrictModel):
    id: str
    name: str = Field(min_length=1, max_length=120)
    location: str = ""
    player_known: bool = True
    attitude: str = "neutral"
    attributes: Attributes = Field(default_factory=Attributes)
    skills: dict[str, int] = Field(default_factory=dict)
    health: Track = Field(default_factory=lambda: Track(current=6, max=6))
    goals: list[str] = Field(default_factory=list)
    plans: list[str] = Field(default_factory=list)
    knows: list[str] = Field(default_factory=list)


class WorldState(StrictModel):
    current_location: str = ""
    situation: str = ""
    locations: dict[str, Location] = Field(default_factory=dict)
    factions: dict[str, Faction] = Field(default_factory=dict)
    clocks: dict[str, Clock] = Field(default_factory=dict)
    facts: dict[str, Fact] = Field(default_factory=dict)


class CampaignMeta(StrictModel):
    id: str
    title: str = Field(min_length=1, max_length=160)
    genre: str = ""
    tone: str = ""
    premise: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    rules_profile: str = "2d6-light"
    narrator_model: str = ""
    turn_count: int = Field(default=0, ge=0)
    world_time_minutes: int = Field(default=0, ge=0)
    content_boundaries: list[str] = Field(default_factory=list)


class RollRecord(StrictModel):
    label: str
    dice: list[int]
    modifier: int
    difficulty: int
    total: int
    outcome: str


class Usage(StrictModel):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_usd: float = 0.0


class TurnRecord(StrictModel):
    turn: int = Field(ge=0)
    kind: TurnKind = "player"
    action: str = ""
    world_time_before: int = 0
    world_time_after: int = 0
    model: str = ""
    usage: Usage = Field(default_factory=Usage)
    rolls: list[RollRecord] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    narration: str = ""


# ---------------------------------------------------------------------------
# Campaign generation drafts
# ---------------------------------------------------------------------------


class ItemDraft(DraftModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: int = Field(default=1, ge=1, le=10_000)
    tags: list[str] = Field(default_factory=list)
    description: str = ""


class CharacterDraft(DraftModel):
    name: str = Field(min_length=1, max_length=120)
    concept: str = ""
    attributes: Attributes = Field(default_factory=Attributes)
    skills: dict[str, int] = Field(default_factory=dict)
    health_max: int = Field(default=7, ge=1, le=20)
    stress_max: int = Field(default=10, ge=1, le=20)
    supplies: int = Field(default=2, ge=0)
    currency: int = Field(default=10, ge=0)
    conditions: list[str] = Field(default_factory=list)
    inventory: list[ItemDraft] = Field(default_factory=list)
    appearance: str = ""
    background: str = ""


class LocationDraft(DraftModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    player_known: bool = True
    tags: list[str] = Field(default_factory=list)


class FactionDraft(DraftModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    goal: str = ""
    stance: str = "neutral"
    resources: dict[str, int] = Field(default_factory=dict)
    player_known: bool = True


class ClockDraft(DraftModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    segments: int = Field(default=4, ge=1, le=20)
    filled: int = Field(default=0, ge=0, le=20)
    trigger: str = ""
    visibility: Visibility = "player"


class FactDraft(DraftModel):
    id: str | None = None
    text: str = Field(min_length=1, max_length=2_000)
    visibility: Visibility = "gm"
    tags: list[str] = Field(default_factory=list)


class NPCDraft(DraftModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    location: str = ""
    player_known: bool = True
    attitude: str = "neutral"
    attributes: Attributes = Field(default_factory=Attributes)
    skills: dict[str, int] = Field(default_factory=dict)
    health_max: int = Field(default=6, ge=1, le=20)
    goals: list[str] = Field(default_factory=list)
    plans: list[str] = Field(default_factory=list)
    knows: list[str] = Field(default_factory=list)
    appearance: str = ""
    secret: str = ""


class CampaignSeed(DraftModel):
    title: str = Field(min_length=1, max_length=160)
    genre: str = ""
    tone: str = ""
    premise: str = ""
    notes: str = ""
    opening_scene: str = Field(min_length=1)
    start_minute: int = Field(default=8 * 60, ge=0, le=1_439)
    current_location: str = Field(min_length=1)
    character: CharacterDraft
    locations: list[LocationDraft] = Field(min_length=1)
    factions: list[FactionDraft] = Field(default_factory=list)
    clocks: list[ClockDraft] = Field(default_factory=list)
    facts: list[FactDraft] = Field(default_factory=list)
    npcs: list[NPCDraft] = Field(default_factory=list)

    @field_validator("locations")
    @classmethod
    def _unique_locations(cls, value: list[LocationDraft]) -> list[LocationDraft]:
        seen = [slugify(item.id) for item in value]
        if len(set(seen)) != len(value):
            raise ValueError("location ids must be unique after slugification")
        return value

    @field_validator("factions")
    @classmethod
    def _unique_factions(cls, value: list[FactionDraft]) -> list[FactionDraft]:
        seen = [slugify(item.id) for item in value]
        if len(set(seen)) != len(value):
            raise ValueError("faction ids must be unique after slugification")
        return value

    @field_validator("clocks")
    @classmethod
    def _unique_clocks(cls, value: list[ClockDraft]) -> list[ClockDraft]:
        seen = [slugify(item.id) for item in value]
        if len(set(seen)) != len(value):
            raise ValueError("clock ids must be unique after slugification")
        return value

    @field_validator("npcs")
    @classmethod
    def _unique_npcs(cls, value: list[NPCDraft]) -> list[NPCDraft]:
        seen = [slugify(item.id) for item in value]
        if len(set(seen)) != len(value):
            raise ValueError("npc ids must be unique after slugification")
        return value

    @field_validator("facts")
    @classmethod
    def _unique_fact_ids(cls, value: list[FactDraft]) -> list[FactDraft]:
        ids = [fact.id for fact in value if fact.id]
        if len(set(ids)) != len(ids):
            raise ValueError("fact ids must be unique")
        return value

    @model_validator(mode="after")
    def _references(self) -> CampaignSeed:
        location_ids = {slugify(item.id) for item in self.locations}
        if slugify(self.current_location) not in location_ids:
            raise ValueError("current_location must reference a generated location")
        for npc in self.npcs:
            if npc.location and slugify(npc.location) not in location_ids:
                raise ValueError(f"npc {npc.id!r} references unknown location {npc.location!r}")

        # Models sometimes omit fact ids or put fact prose in an NPC's `knows`
        # list. Assign stable ids, then resolve ids or exact fact text to ids.
        used: set[str] = set()
        for fact in self.facts:
            raw_id = fact.id.strip() if fact.id else ""
            base = raw_id or f"fact_{slugify(fact.text)[:48]}"
            candidate = base
            suffix = 2
            while candidate in used:
                candidate = f"{base}_{suffix}"
                suffix += 1
            fact.id = candidate
            used.add(candidate)

        by_text: dict[str, str] = {}
        for fact in self.facts:
            if fact.id is not None:
                by_text[_normalize_fact_text(fact.text)] = fact.id

        for npc in self.npcs:
            resolved: list[str] = []
            for reference in npc.knows:
                if reference in used:
                    resolved.append(reference)
                    continue
                normalized = _normalize_fact_text(reference)
                if normalized in by_text:
                    resolved.append(by_text[normalized])
                    continue
                matches = [
                    fact_id
                    for text, fact_id in by_text.items()
                    if len(normalized) >= 12 and (normalized in text or text in normalized)
                ]
                if len(set(matches)) == 1:
                    resolved.append(matches[0])
                    continue
                raise ValueError(
                    f"npc {npc.id!r} knows unknown fact {reference!r}; "
                    "use a fact id or the exact fact text"
                )
            npc.knows = resolved

        names = [_normalize_fact_text(self.character.name)]
        names.extend(_normalize_fact_text(npc.name) for npc in self.npcs)
        if len(set(names)) != len(names):
            raise ValueError("the player character and every NPC must have a distinct name")
        return self


@dataclass
class CampaignState:
    root: Path
    meta: CampaignMeta
    character: Character
    world: WorldState
    npcs: dict[str, NPC] = field(default_factory=dict)
    journal: str = ""
    campaign_body: str = ""
    character_body: str = ""
    world_body: str = ""
    npc_bodies: dict[str, str] = field(default_factory=dict)
    turns: list[TurnRecord] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.meta.id

    def all_fact_ids(self) -> set[str]:
        return set(self.world.facts)

    def all_npc_ids(self) -> set[str]:
        return set(self.npcs)


def utc_now() -> datetime:
    return datetime.now(UTC)


def dump_json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value
