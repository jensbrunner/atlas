"""Structured intent and outcome contracts.

These are the only shapes that may cross the boundary between an intent source
(a parser, a scripted test, or later a language model) and the deterministic
rules engine. Both are closed schemas: unknown fields and unknown command types
are rejected before they can touch world state.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atlas.domain.commands import DomainCommand
from atlas.domain.rules import RollSummary


class IntentKind(StrEnum):
    MOVE = "move"
    OBSERVE = "observe"
    SEARCH = "search"
    SPEAK = "speak"
    WAIT = "wait"
    NEGOTIATE = "negotiate"
    ENGINEER = "engineer"
    CONFRONT = "confront"
    GATHER = "gather"
    GIVE = "give"
    ABANDON = "abandon"


class IntentProposal(BaseModel):
    """A validated statement of what the player is trying to do."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    kind: IntentKind
    actor_id: str = Field(min_length=3, max_length=64)
    target_id: str | None = Field(default=None, min_length=3, max_length=64)
    target_slug: str | None = Field(default=None, min_length=1, max_length=80)
    item_slug: str | None = Field(default=None, min_length=1, max_length=80)
    quantity: int = Field(default=1, ge=1, le=999)
    requested_minutes: int | None = Field(default=None, ge=1, le=10_080)
    text: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def _required_fields(self) -> IntentProposal:
        targeted = {
            IntentKind.MOVE,
            IntentKind.SPEAK,
            IntentKind.NEGOTIATE,
            IntentKind.CONFRONT,
            IntentKind.ENGINEER,
            IntentKind.GATHER,
            IntentKind.GIVE,
        }
        if self.kind in targeted and self.target_id is None:
            raise ValueError(f"{self.kind.value} intents require a target_id")
        if self.kind is IntentKind.GIVE and self.item_slug is None:
            raise ValueError("give intents require an item_slug")
        if self.kind is IntentKind.WAIT and self.requested_minutes is None:
            raise ValueError("wait intents require requested_minutes")
        return self


class ObservationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4_000)
    kind: Literal[
        "arrival",
        "search",
        "speech",
        "observation",
        "wait",
        "discovery",
        "negotiation",
        "engineering",
        "confrontation",
        "ending",
    ] = "observation"
    subject_ids: list[str] = Field(default_factory=list)


class OutcomeProposal(BaseModel):
    """The deterministic result of adjudicating one intent.

    ``commands`` are typed domain commands, never raw model text. The turn
    service re-validates them against the committed projection immediately
    before the atomic write.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    actor_id: str = Field(min_length=3, max_length=64)
    kind: IntentKind
    resolution: Literal["automatic", "success", "mixed_success", "failure"]
    roll: RollSummary | None = None
    commands: list[DomainCommand] = Field(default_factory=list)
    elapsed_minutes: int = Field(default=0, ge=0, le=10_080)
    observations: list[ObservationProposal] = Field(default_factory=list)
    summary: str = Field(min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def _resolution_matches_roll(self) -> OutcomeProposal:
        if self.roll is None and self.resolution != "automatic":
            raise ValueError("a non-automatic outcome requires a roll")
        if self.roll is not None and self.resolution != self.roll.outcome.value:
            raise ValueError("outcome resolution must match the roll band")
        return self
