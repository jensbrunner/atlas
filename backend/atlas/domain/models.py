"""Pydantic domain models for durable campaign state."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntityKind(StrEnum):
    PLAYER_CHARACTER = "player_character"
    NPC = "npc"
    LOCATION = "location"
    ITEM = "item"
    FACTION = "faction"


class CampaignStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class Visibility(StrEnum):
    PUBLIC = "PUBLIC"
    GM_ONLY = "GM_ONLY"
    ACTOR_PRIVATE = "ACTOR_PRIVATE"
    PLAYER_KNOWN = "PLAYER_KNOWN"


class ResourceName(StrEnum):
    HEALTH = "health"
    STRESS = "stress"
    SUPPLIES = "supplies"
    CURRENCY = "currency"


class TurnStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PARSED = "PARSED"
    RESOLVED = "RESOLVED"
    NARRATED = "NARRATED"
    VALIDATED = "VALIDATED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"


class CampaignSettings(StrictModel):
    tone: str = "classic fantasy"
    prose_length: str = "medium"
    mechanics_visibility: str = "on_request"
    hard_avoids: list[str] = Field(default_factory=list)
    soft_avoids: list[str] = Field(default_factory=list)


class Campaign(StrictModel):
    id: str
    title: str = Field(min_length=1, max_length=200)
    rules_version: str = "0.1"
    status: CampaignStatus = CampaignStatus.ACTIVE
    state_version: int = Field(default=0, ge=0)
    current_time: int = Field(default=0, ge=0)
    seed: int
    settings: CampaignSettings = Field(default_factory=CampaignSettings)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Entity(StrictModel):
    id: str
    campaign_id: str
    kind: EntityKind
    slug: str
    display_name: str
    static: dict[str, Any] = Field(default_factory=dict)
    created_event_id: str | None = None
    retired_event_id: str | None = None


class EntityState(StrictModel):
    entity_id: str
    campaign_id: str
    version: int = Field(ge=1)
    state: dict[str, Any] = Field(default_factory=dict)


class Checkpoint(StrictModel):
    id: str
    campaign_id: str
    event_seq: int = Field(ge=0)
    state_hash: str
    snapshot: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StoredTurn(StrictModel):
    id: str
    campaign_id: str
    client_action_id: str
    ordinal: int = Field(ge=1)
    player_text: str
    status: TurnStatus
    snapshot_version: int = Field(ge=0)
    narration: str | None = None
    mechanics: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
