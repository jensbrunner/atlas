"""Typed, append-only event envelopes.

The event schema is versioned and validated before any projection changes. A
model or caller cannot introduce an unknown event type or an invalid payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from atlas.domain.models import (
    EntityKind,
    RelationshipDimension,
    ResourceName,
    StatementKind,
    Visibility,
)


class EventType(StrEnum):
    ENTITY_CREATED = "entity.created"
    RESOURCE_CHANGED = "entity.resource_changed"
    ENTITY_MOVED = "entity.moved"
    TIME_ADVANCED = "time.advanced"
    SCENE_OBSERVED = "scene.observed"
    FACT_RECORDED = "fact.recorded"
    STATEMENT_RECORDED = "statement.recorded"
    KNOWLEDGE_RECORDED = "knowledge.recorded"
    RELATIONSHIP_CHANGED = "relationship.changed"
    CLOCK_CREATED = "clock.created"
    CLOCK_ADVANCED = "clock.advanced"
    ITEM_TRANSFERRED = "item.transferred"
    ITEM_GIVEN = "item.given"
    ITEM_CONSUMED = "item.consumed"
    ENTITY_FLAG_SET = "entity.flag_set"
    CAMPAIGN_ENDED = "campaign.ended"
    TURN_COMMITTED = "turn.committed"


def _strict() -> ConfigDict:
    return ConfigDict(extra="forbid")


class EntityCreatedPayload(BaseModel):
    model_config = _strict()

    kind: EntityKind
    slug: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=200)
    static: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)


class ResourceChangedPayload(BaseModel):
    model_config = _strict()

    resource: ResourceName
    delta: int
    before: int
    after: int
    min: int
    max: int
    reason: str = Field(min_length=1, max_length=300)


class EntityMovedPayload(BaseModel):
    model_config = _strict()

    from_location_id: str
    to_location_id: str
    reason: str = Field(min_length=1, max_length=300)


class TimeAdvancedPayload(BaseModel):
    model_config = _strict()

    minutes: int = Field(gt=0)
    before: int = Field(ge=0)
    after: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=300)


class TurnCommittedPayload(BaseModel):
    model_config = _strict()

    turn_id: str
    ordinal: int = Field(ge=1)
    state_version: int = Field(ge=1)


class SceneObservedPayload(BaseModel):
    model_config = _strict()

    text: str = Field(min_length=1, max_length=4000)
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


class FactRecordedPayload(BaseModel):
    model_config = _strict()

    fact_slug: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=1_000)
    visibility: Visibility = Visibility.GM_ONLY


class StatementRecordedPayload(BaseModel):
    model_config = _strict()

    statement_slug: str = Field(min_length=1, max_length=80)
    speaker_id: str
    proposition: str = Field(min_length=1, max_length=1_000)
    topic: str = Field(min_length=1, max_length=80)
    kind: StatementKind = StatementKind.CLAIM
    is_true: bool
    audience_ids: list[str] = Field(default_factory=list)


class KnowledgeRecordedPayload(BaseModel):
    model_config = _strict()

    entity_id: str
    statement_slug: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=80)


class RelationshipChangedPayload(BaseModel):
    model_config = _strict()

    from_id: str
    to_id: str
    dimension: RelationshipDimension
    before: int
    after: int


class ClockCreatedPayload(BaseModel):
    model_config = _strict()

    clock_slug: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    segments: int = Field(ge=1, le=20)
    filled: int = Field(ge=0, le=20)
    trigger: str = Field(min_length=1, max_length=300)
    owner_id: str | None = None
    visibility: Visibility = Visibility.PUBLIC


class ClockAdvancedPayload(BaseModel):
    model_config = _strict()

    clock_slug: str = Field(min_length=1, max_length=80)
    delta: int
    before: int
    after: int
    reason: str = Field(min_length=1, max_length=300)


class ItemTransferredPayload(BaseModel):
    model_config = _strict()

    item_id: str
    item_slug: str = Field(min_length=1, max_length=80)
    item_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1)
    from_location_id: str | None = None
    to_entity_id: str


class ItemConsumedPayload(BaseModel):
    model_config = _strict()

    holder_id: str
    item_slug: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1)


class ItemGivenPayload(BaseModel):
    model_config = _strict()

    holder_id: str
    recipient_id: str
    item_slug: str = Field(min_length=1, max_length=80)
    item_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1)


class EntityFlagSetPayload(BaseModel):
    model_config = _strict()

    key: str = Field(min_length=1, max_length=64)
    before: Any = None
    after: Any = None


class CampaignEndedPayload(BaseModel):
    model_config = _strict()

    outcome: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=2_000)


PAYLOAD_MODELS: dict[EventType, type[BaseModel]] = {
    EventType.ENTITY_CREATED: EntityCreatedPayload,
    EventType.RESOURCE_CHANGED: ResourceChangedPayload,
    EventType.ENTITY_MOVED: EntityMovedPayload,
    EventType.TIME_ADVANCED: TimeAdvancedPayload,
    EventType.SCENE_OBSERVED: SceneObservedPayload,
    EventType.FACT_RECORDED: FactRecordedPayload,
    EventType.STATEMENT_RECORDED: StatementRecordedPayload,
    EventType.KNOWLEDGE_RECORDED: KnowledgeRecordedPayload,
    EventType.RELATIONSHIP_CHANGED: RelationshipChangedPayload,
    EventType.CLOCK_CREATED: ClockCreatedPayload,
    EventType.CLOCK_ADVANCED: ClockAdvancedPayload,
    EventType.ITEM_TRANSFERRED: ItemTransferredPayload,
    EventType.ITEM_GIVEN: ItemGivenPayload,
    EventType.ITEM_CONSUMED: ItemConsumedPayload,
    EventType.ENTITY_FLAG_SET: EntityFlagSetPayload,
    EventType.CAMPAIGN_ENDED: CampaignEndedPayload,
    EventType.TURN_COMMITTED: TurnCommittedPayload,
}


class Provenance(BaseModel):
    model_config = _strict()

    authority: Literal["seed", "rules_engine", "player_command", "system"]
    rules_version: str = "0.1"
    note: str | None = None


class EventEnvelope(BaseModel):
    """The durable event shape stored in SQLite."""

    model_config = _strict()

    schema_version: Literal[1] = 1
    event_id: str
    campaign_id: str
    turn_id: str | None = None
    sequence: int = Field(ge=1)
    event_type: EventType
    world_time: int = Field(ge=0)
    actor_id: str | None = None
    subject_id: str | None = None
    cause_event_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any]
    visibility: Visibility = Visibility.PUBLIC
    provenance: Provenance

    def parsed_payload(self) -> BaseModel:
        return parse_event_payload(self.event_type, self.payload)


def parse_event_payload(event_type: EventType | str, payload: dict[str, Any]) -> BaseModel:
    """Validate ``payload`` against the schema registered for ``event_type``."""
    try:
        resolved = EventType(event_type)
    except ValueError as exc:
        raise EventValidationError(f"unknown event type: {event_type!r}") from exc

    model = PAYLOAD_MODELS[resolved]
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise EventValidationError(f"invalid payload for {resolved.value}: {exc.errors()}") from exc


def validate_envelope(envelope: EventEnvelope) -> BaseModel:
    return parse_event_payload(envelope.event_type, envelope.payload)


class EventValidationError(ValueError):
    """Raised when an event type or payload is not accepted by the schema."""


@dataclass(frozen=True, slots=True)
class EventDraft:
    """An event proposed by the rules engine before sequence/id assignment."""

    event_type: EventType
    payload: BaseModel
    world_time: int
    actor_id: str | None = None
    subject_id: str | None = None
    visibility: Visibility = Visibility.PUBLIC
    cause_event_ids: list[str] = field(default_factory=list)

    def to_envelope(
        self,
        *,
        event_id: str,
        campaign_id: str,
        sequence: int,
        turn_id: str | None,
        provenance: Provenance,
    ) -> EventEnvelope:
        parsed = parse_event_payload(self.event_type, self.payload.model_dump(mode="json"))
        return EventEnvelope(
            event_id=event_id,
            campaign_id=campaign_id,
            turn_id=turn_id,
            sequence=sequence,
            event_type=self.event_type,
            world_time=self.world_time,
            actor_id=self.actor_id,
            subject_id=self.subject_id,
            cause_event_ids=self.cause_event_ids,
            payload=parsed.model_dump(mode="json"),
            visibility=self.visibility,
            provenance=provenance,
        )
