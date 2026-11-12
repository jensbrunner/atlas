from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateCampaignBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    prompt: str = ""
    genre: str = ""
    tone: str = ""
    character: str = ""


class PlayTurnBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=4_000)


class WorldTurnBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = ""


def error_body(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}
