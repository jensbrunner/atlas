from __future__ import annotations

from datetime import datetime

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
