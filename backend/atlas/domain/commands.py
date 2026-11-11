"""Typed domain commands accepted by the rules engine.

Commands are the only way ordinary gameplay mutates world state. The shapes are
closed: unknown fields and unknown command kinds are rejected before execution.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationInfo, field_validator

from atlas.domain.models import (
    EntityKind,
    RelationshipDimension,
    ResourceName,
    StatementKind,
    Visibility,
)


class _Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateEntityCommand(_Command):
    type: Literal["create_entity"] = "create_entity"
    kind: EntityKind
    slug: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    display_name: str = Field(min_length=1, max_length=200)
    static: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=300)


class AdjustResourceCommand(_Command):
    type: Literal["adjust_resource"] = "adjust_resource"
    entity_id: str = Field(min_length=3)
    resource: ResourceName
    delta: int
    reason: str = Field(min_length=1, max_length=300)

    @field_validator("delta")
    @classmethod
    def _non_zero_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("delta must be non-zero")
        return value


class MoveEntityCommand(_Command):
    type: Literal["move_entity"] = "move_entity"
    entity_id: str = Field(min_length=3)
    to_location_id: str = Field(min_length=3)
    reason: str = Field(min_length=1, max_length=300)


class AdvanceTimeCommand(_Command):
    type: Literal["advance_time"] = "advance_time"
    minutes: int = Field(ge=1, le=10_080)
    reason: str = Field(min_length=1, max_length=300)


class CreateFactCommand(_Command):
    """A canonical fact. Facts are GM truth, not statements or beliefs."""

    type: Literal["create_fact"] = "create_fact"
    fact_slug: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    text: str = Field(min_length=1, max_length=1_000)
    visibility: Visibility = Visibility.GM_ONLY
    reason: str = Field(min_length=1, max_length=300)


class RecordStatementCommand(_Command):
    """A claim made by an entity. ``is_true`` is GM truth, never player data."""

    type: Literal["record_statement"] = "record_statement"
    statement_slug: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    speaker_id: str = Field(min_length=3)
    proposition: str = Field(min_length=1, max_length=1_000)
    topic: str = Field(min_length=1, max_length=80)
    kind: StatementKind = StatementKind.CLAIM
    is_true: bool
    audience_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=300)


class LearnStatementCommand(_Command):
    type: Literal["learn_statement"] = "learn_statement"
    entity_id: str = Field(min_length=3)
    statement_slug: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    source: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=300)


class ChangeRelationshipCommand(_Command):
    type: Literal["change_relationship"] = "change_relationship"
    from_id: str = Field(min_length=3)
    to_id: str = Field(min_length=3)
    dimension: RelationshipDimension = RelationshipDimension.TRUST
    delta: int = Field(ge=-3, le=3)
    reason: str = Field(min_length=1, max_length=300)

    @field_validator("delta")
    @classmethod
    def _non_zero_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("delta must be non-zero")
        return value


class CreateClockCommand(_Command):
    type: Literal["create_clock"] = "create_clock"
    clock_slug: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    name: str = Field(min_length=1, max_length=200)
    segments: int = Field(ge=1, le=20)
    filled: int = Field(default=0, ge=0, le=20)
    trigger: str = Field(min_length=1, max_length=300)
    owner_id: str | None = Field(default=None, min_length=3)
    visibility: Visibility = Visibility.PUBLIC
    reason: str = Field(min_length=1, max_length=300)

    @field_validator("filled")
    @classmethod
    def _filled_within_segments(cls, value: int, info: ValidationInfo) -> int:
        segments = info.data.get("segments")
        if isinstance(segments, int) and value > segments:
            raise ValueError("filled must not exceed segments")
        return value


class AdvanceClockCommand(_Command):
    type: Literal["advance_clock"] = "advance_clock"
    clock_slug: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    delta: int = Field(ge=-20, le=20)
    reason: str = Field(min_length=1, max_length=300)

    @field_validator("delta")
    @classmethod
    def _non_zero_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("delta must be non-zero")
        return value


class TransferItemCommand(_Command):
    type: Literal["transfer_item"] = "transfer_item"
    item_id: str = Field(min_length=3)
    to_entity_id: str = Field(min_length=3)
    quantity: int = Field(ge=1, le=999)
    reason: str = Field(min_length=1, max_length=300)


class GiveItemCommand(_Command):
    """Move carried inventory from one character to another."""

    type: Literal["give_item"] = "give_item"
    holder_id: str = Field(min_length=3)
    recipient_id: str = Field(min_length=3)
    item_slug: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=999)
    reason: str = Field(min_length=1, max_length=300)


class ConsumeItemCommand(_Command):
    type: Literal["consume_item"] = "consume_item"
    holder_id: str = Field(min_length=3)
    item_slug: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=999)
    reason: str = Field(min_length=1, max_length=300)


class SetEntityFlagCommand(_Command):
    type: Literal["set_entity_flag"] = "set_entity_flag"
    entity_id: str = Field(min_length=3)
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    value: bool | int | str
    reason: str = Field(min_length=1, max_length=300)


class EndCampaignCommand(_Command):
    type: Literal["end_campaign"] = "end_campaign"
    outcome: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    summary: str = Field(min_length=1, max_length=2_000)
    reason: str = Field(min_length=1, max_length=300)


DomainCommand = Annotated[
    CreateEntityCommand
    | AdjustResourceCommand
    | MoveEntityCommand
    | AdvanceTimeCommand
    | CreateFactCommand
    | RecordStatementCommand
    | LearnStatementCommand
    | ChangeRelationshipCommand
    | CreateClockCommand
    | AdvanceClockCommand
    | TransferItemCommand
    | GiveItemCommand
    | ConsumeItemCommand
    | SetEntityFlagCommand
    | EndCampaignCommand,
    Field(discriminator="type"),
]

DOMAIN_COMMAND_ADAPTER: TypeAdapter[DomainCommand] = TypeAdapter(DomainCommand)


def parse_domain_command(value: dict[str, Any]) -> DomainCommand:
    return DOMAIN_COMMAND_ADAPTER.validate_python(value)
