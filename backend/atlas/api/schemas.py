from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CampaignCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    seed: int | None = None


class CampaignResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    rules_version: str
    status: str
    state_version: int
    current_time: int
    seed: int
    created_at: datetime


class CampaignListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaigns: list[CampaignResponse]


class TurnCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_action_id: str = Field(min_length=36, max_length=36)
    player_text: str = Field(min_length=1, max_length=8_000)
    expected_version: int | None = Field(default=None, ge=0)


class RollResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    dice: list[int]
    modifier: int
    difficulty: int
    total: int
    outcome: str
    rng_algorithm: str


class ObservationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    sequence: int
    turn_id: str | None
    world_time: int
    text: str
    kind: str
    subject_ids: list[str]
    visibility: str


class TurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    campaign_id: str
    client_action_id: str
    ordinal: int
    player_text: str
    status: str
    snapshot_version: int
    campaign_version: int
    narration: str
    mechanics: dict[str, Any]
    roll: RollResponse | None = None
    observations: list[ObservationResponse] = Field(default_factory=list)
    error_code: str | None = None
    created_at: datetime
    committed_at: datetime | None = None


class TurnListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turns: list[TurnResponse]
    next_cursor: int | None = None


class StateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str
    current_time: int
    state_version: int
    scene: dict[str, Any]
    entities: list[dict[str, Any]]
    recent_observations: list[ObservationResponse] = Field(default_factory=list)


class JournalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[ObservationResponse]
    next_cursor: int | None = None
