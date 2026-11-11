"""Typed domain commands accepted by the rules engine.

Commands are the only way ordinary gameplay mutates world state. The shapes are
closed: unknown fields and unknown command kinds are rejected before execution.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from atlas.domain.models import EntityKind, ResourceName


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


DomainCommand = Annotated[
    CreateEntityCommand | AdjustResourceCommand | MoveEntityCommand | AdvanceTimeCommand,
    Field(discriminator="type"),
]

DOMAIN_COMMAND_ADAPTER: TypeAdapter[DomainCommand] = TypeAdapter(DomainCommand)


def parse_domain_command(value: dict[str, Any]) -> DomainCommand:
    return DOMAIN_COMMAND_ADAPTER.validate_python(value)
