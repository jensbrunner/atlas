"""In-memory world-state projection derived solely from committed events."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from atlas.domain.errors import InvariantViolation
from atlas.domain.events import EventEnvelope, EventType, parse_event_payload
from atlas.domain.models import (
    CampaignStatus,
    EntityKind,
    RelationshipDimension,
    StatementKind,
    Visibility,
)

SCHEMA_VERSION = 1


@dataclass(slots=True)
class ProjectedEntity:
    id: str
    campaign_id: str
    kind: EntityKind
    slug: str
    display_name: str
    static: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    state_version: int = 1
    created_event_id: str | None = None
    retired_event_id: str | None = None


@dataclass(slots=True)
class ProjectedObservation:
    event_id: str
    campaign_id: str
    sequence: int
    turn_id: str | None
    world_time: int
    text: str
    kind: str
    subject_ids: list[str] = field(default_factory=list)
    visibility: Visibility = Visibility.PUBLIC


@dataclass(slots=True)
class ProjectedFact:
    slug: str
    text: str
    visibility: Visibility
    event_id: str


@dataclass(slots=True)
class ProjectedStatement:
    slug: str
    speaker_id: str
    proposition: str
    topic: str
    kind: StatementKind
    is_true: bool
    audience_ids: list[str]
    event_id: str


@dataclass(slots=True)
class ProjectedKnowledge:
    entity_id: str
    statement_slug: str
    source: str
    event_id: str


@dataclass(slots=True)
class ProjectedRelationship:
    from_id: str
    to_id: str
    dimension: RelationshipDimension
    value: int
    updated_event_id: str


@dataclass(slots=True)
class ProjectedClock:
    slug: str
    name: str
    segments: int
    filled: int
    trigger: str
    owner_id: str | None
    visibility: Visibility
    created_event_id: str


@dataclass(slots=True)
class ProjectedEnding:
    outcome: str
    summary: str
    event_id: str


@dataclass(slots=True)
class ProjectionState:
    campaign_id: str
    current_time: int = 0
    state_version: int = 0
    last_event_seq: int = 0
    status: CampaignStatus = CampaignStatus.ACTIVE
    entities: dict[str, ProjectedEntity] = field(default_factory=dict)
    observations: list[ProjectedObservation] = field(default_factory=list)
    facts: dict[str, ProjectedFact] = field(default_factory=dict)
    statements: dict[str, ProjectedStatement] = field(default_factory=dict)
    knowledge: dict[tuple[str, str], ProjectedKnowledge] = field(default_factory=dict)
    relationships: dict[tuple[str, str, RelationshipDimension], ProjectedRelationship] = field(
        default_factory=dict
    )
    clocks: dict[str, ProjectedClock] = field(default_factory=dict)
    ending: ProjectedEnding | None = None

    def clone(self) -> ProjectionState:
        return copy.deepcopy(self)

    def entity_by_slug(self, slug: str) -> ProjectedEntity | None:
        for entity in self.entities.values():
            if entity.slug == slug:
                return entity
        return None

    def knows(self, entity_id: str, statement_slug: str) -> bool:
        return (entity_id, statement_slug) in self.knowledge

    def relationship_value(
        self,
        from_id: str,
        to_id: str,
        dimension: RelationshipDimension = RelationshipDimension.TRUST,
    ) -> int:
        relationship = self.relationships.get((from_id, to_id, dimension))
        return relationship.value if relationship is not None else 0

    def require_entity(self, entity_id: str) -> ProjectedEntity:
        entity = self.entities.get(entity_id)
        if entity is None:
            raise InvariantViolation(
                "unknown_entity",
                f"entity {entity_id!r} does not exist in this campaign",
                entity_id=entity_id,
            )
        return entity

    def require_location(self, location_id: str) -> ProjectedEntity:
        location = self.require_entity(location_id)
        if location.kind is not EntityKind.LOCATION:
            raise InvariantViolation(
                "not_a_location",
                f"entity {location_id!r} is not a location",
                entity_id=location_id,
                kind=location.kind.value,
            )
        return location


def apply_event(projection: ProjectionState, envelope: EventEnvelope) -> None:
    """Apply one validated event. Raises on any integrity mismatch."""
    if envelope.schema_version != SCHEMA_VERSION:
        raise InvariantViolation(
            "unsupported_schema",
            f"unsupported event schema version {envelope.schema_version}",
        )
    if envelope.campaign_id != projection.campaign_id:
        raise InvariantViolation(
            "wrong_campaign",
            "event belongs to a different campaign",
            expected=projection.campaign_id,
            actual=envelope.campaign_id,
        )
    if envelope.sequence != projection.last_event_seq + 1:
        raise InvariantViolation(
            "event_sequence",
            "event sequences must be contiguous within a campaign",
            expected=projection.last_event_seq + 1,
            received=envelope.sequence,
        )

    payload = parse_event_payload(envelope.event_type, envelope.payload)

    if envelope.event_type is EventType.ENTITY_CREATED:
        _apply_entity_created(projection, envelope, payload)
    elif envelope.event_type is EventType.RESOURCE_CHANGED:
        _apply_resource_changed(projection, envelope, payload)
    elif envelope.event_type is EventType.ENTITY_MOVED:
        _apply_entity_moved(projection, envelope, payload)
    elif envelope.event_type is EventType.TIME_ADVANCED:
        _apply_time_advanced(projection, envelope, payload)
    elif envelope.event_type is EventType.SCENE_OBSERVED:
        _apply_scene_observed(projection, envelope, payload)
    elif envelope.event_type is EventType.FACT_RECORDED:
        _apply_fact_recorded(projection, envelope, payload)
    elif envelope.event_type is EventType.STATEMENT_RECORDED:
        _apply_statement_recorded(projection, envelope, payload)
    elif envelope.event_type is EventType.KNOWLEDGE_RECORDED:
        _apply_knowledge_recorded(projection, envelope, payload)
    elif envelope.event_type is EventType.RELATIONSHIP_CHANGED:
        _apply_relationship_changed(projection, envelope, payload)
    elif envelope.event_type is EventType.CLOCK_CREATED:
        _apply_clock_created(projection, envelope, payload)
    elif envelope.event_type is EventType.CLOCK_ADVANCED:
        _apply_clock_advanced(projection, envelope, payload)
    elif envelope.event_type is EventType.ITEM_TRANSFERRED:
        _apply_item_transferred(projection, envelope, payload)
    elif envelope.event_type is EventType.ITEM_CONSUMED:
        _apply_item_consumed(projection, envelope, payload)
    elif envelope.event_type is EventType.ITEM_GIVEN:
        _apply_item_given(projection, envelope, payload)
    elif envelope.event_type is EventType.ENTITY_FLAG_SET:
        _apply_entity_flag_set(projection, envelope, payload)
    elif envelope.event_type is EventType.CAMPAIGN_ENDED:
        _apply_campaign_ended(projection, envelope, payload)
    elif envelope.event_type is EventType.TURN_COMMITTED:
        _apply_turn_committed(projection, envelope, payload)
    else:
        raise InvariantViolation("unknown_event", f"unhandled event type {envelope.event_type!r}")

    projection.last_event_seq = envelope.sequence


def _apply_entity_created(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    if envelope.subject_id is None:
        raise InvariantViolation("missing_subject", "entity.created requires a subject_id")
    if envelope.subject_id in projection.entities:
        raise InvariantViolation(
            "duplicate_entity", f"entity {envelope.subject_id!r} already exists"
        )
    if projection.entity_by_slug(payload.slug) is not None:
        raise InvariantViolation("duplicate_slug", f"slug {payload.slug!r} already exists")

    projection.entities[envelope.subject_id] = ProjectedEntity(
        id=envelope.subject_id,
        campaign_id=projection.campaign_id,
        kind=payload.kind,
        slug=payload.slug,
        display_name=payload.display_name,
        static=copy.deepcopy(payload.static),
        state=copy.deepcopy(payload.state),
        state_version=1,
        created_event_id=envelope.event_id,
    )


def _apply_resource_changed(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    entity = projection.require_entity(envelope.subject_id or "")
    current = entity.state[payload.resource.value]
    if current != payload.before:
        raise InvariantViolation(
            "stale_resource_state",
            "resource before-value does not match projection",
            expected=current,
            received=payload.before,
        )
    if payload.after != payload.before + payload.delta:
        raise InvariantViolation("resource_delta", "resource delta does not match before/after")
    if not payload.min <= payload.after <= payload.max:
        raise InvariantViolation(
            "resource_bounds",
            "resource change leaves its allowed bounds",
            resource=payload.resource.value,
            after=payload.after,
            min=payload.min,
            max=payload.max,
        )
    entity.state[payload.resource.value] = payload.after
    entity.state_version += 1


def _apply_entity_moved(projection: ProjectionState, envelope: EventEnvelope, payload: Any) -> None:
    entity = projection.require_entity(envelope.subject_id or "")
    projection.require_location(payload.to_location_id)
    if entity.state.get("location_id") != payload.from_location_id:
        raise InvariantViolation(
            "stale_location",
            "entity is not at the expected origin location",
            expected=entity.state.get("location_id"),
            received=payload.from_location_id,
        )
    if payload.from_location_id == payload.to_location_id:
        raise InvariantViolation("same_location", "entity is already at the destination")
    entity.state["location_id"] = payload.to_location_id
    entity.state_version += 1


def _apply_time_advanced(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    if projection.current_time != payload.before:
        raise InvariantViolation(
            "stale_time",
            "time before-value does not match projection",
            expected=projection.current_time,
            received=payload.before,
        )
    if payload.after != payload.before + payload.minutes:
        raise InvariantViolation("time_step", "time advancement does not match minutes")
    projection.current_time = payload.after


def _apply_turn_committed(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    if envelope.turn_id != payload.turn_id:
        raise InvariantViolation("turn_mismatch", "turn.committed turn_id does not match envelope")
    if payload.state_version != projection.state_version + 1:
        raise InvariantViolation(
            "version_step",
            "turn commit must increment the campaign version by exactly one",
            current=projection.state_version,
            proposed=payload.state_version,
        )
    projection.state_version = payload.state_version


def _apply_scene_observed(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    for subject_id in payload.subject_ids:
        projection.require_entity(subject_id)
    projection.observations.append(
        ProjectedObservation(
            event_id=envelope.event_id,
            campaign_id=projection.campaign_id,
            sequence=envelope.sequence,
            turn_id=envelope.turn_id,
            world_time=envelope.world_time,
            text=payload.text,
            kind=payload.kind,
            subject_ids=list(payload.subject_ids),
            visibility=envelope.visibility,
        )
    )


def _apply_fact_recorded(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    if payload.fact_slug in projection.facts:
        raise InvariantViolation(
            "duplicate_fact",
            f"fact {payload.fact_slug!r} is already recorded",
            slug=payload.fact_slug,
        )
    projection.facts[payload.fact_slug] = ProjectedFact(
        slug=payload.fact_slug,
        text=payload.text,
        visibility=payload.visibility,
        event_id=envelope.event_id,
    )


def _apply_statement_recorded(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    if payload.statement_slug in projection.statements:
        raise InvariantViolation(
            "duplicate_statement",
            f"statement {payload.statement_slug!r} is already recorded",
            slug=payload.statement_slug,
        )
    projection.require_entity(payload.speaker_id)
    for audience_id in payload.audience_ids:
        projection.require_entity(audience_id)
    statement = ProjectedStatement(
        slug=payload.statement_slug,
        speaker_id=payload.speaker_id,
        proposition=payload.proposition,
        topic=payload.topic,
        kind=payload.kind,
        is_true=payload.is_true,
        audience_ids=list(payload.audience_ids),
        event_id=envelope.event_id,
    )
    projection.statements[statement.slug] = statement
    # A speaker necessarily knows what they just said.
    projection.knowledge[(statement.speaker_id, statement.slug)] = ProjectedKnowledge(
        entity_id=statement.speaker_id,
        statement_slug=statement.slug,
        source="statement",
        event_id=envelope.event_id,
    )


def _apply_knowledge_recorded(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    projection.require_entity(payload.entity_id)
    statement = projection.statements.get(payload.statement_slug)
    if statement is None:
        raise InvariantViolation(
            "unknown_statement",
            f"statement {payload.statement_slug!r} does not exist",
            slug=payload.statement_slug,
        )
    key = (payload.entity_id, payload.statement_slug)
    if key in projection.knowledge:
        # Re-learning the same statement is a no-op, not an inconsistency.
        return
    projection.knowledge[key] = ProjectedKnowledge(
        entity_id=payload.entity_id,
        statement_slug=payload.statement_slug,
        source=payload.source,
        event_id=envelope.event_id,
    )


def _apply_relationship_changed(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    projection.require_entity(payload.from_id)
    projection.require_entity(payload.to_id)
    key = (payload.from_id, payload.to_id, payload.dimension)
    current = projection.relationships.get(key)
    before = current.value if current is not None else 0
    if before != payload.before:
        raise InvariantViolation(
            "stale_relationship",
            "relationship before-value does not match projection",
            expected=before,
            received=payload.before,
        )
    if not -5 <= payload.after <= 5:
        raise InvariantViolation(
            "relationship_bounds",
            "relationship value left the supported range",
            after=payload.after,
        )
    projection.relationships[key] = ProjectedRelationship(
        from_id=payload.from_id,
        to_id=payload.to_id,
        dimension=payload.dimension,
        value=payload.after,
        updated_event_id=envelope.event_id,
    )


def _apply_clock_created(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    if payload.clock_slug in projection.clocks:
        raise InvariantViolation(
            "duplicate_clock",
            f"clock {payload.clock_slug!r} already exists",
            slug=payload.clock_slug,
        )
    if not 0 <= payload.filled <= payload.segments:
        raise InvariantViolation(
            "clock_bounds",
            "initial clock fill must be within its segment count",
            filled=payload.filled,
            segments=payload.segments,
        )
    if payload.owner_id is not None:
        projection.require_entity(payload.owner_id)
    projection.clocks[payload.clock_slug] = ProjectedClock(
        slug=payload.clock_slug,
        name=payload.name,
        segments=payload.segments,
        filled=payload.filled,
        trigger=payload.trigger,
        owner_id=payload.owner_id,
        visibility=payload.visibility,
        created_event_id=envelope.event_id,
    )


def _apply_clock_advanced(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    clock = projection.clocks.get(payload.clock_slug)
    if clock is None:
        raise InvariantViolation(
            "unknown_clock",
            f"clock {payload.clock_slug!r} does not exist",
            slug=payload.clock_slug,
        )
    if clock.filled != payload.before:
        raise InvariantViolation(
            "stale_clock",
            "clock before-value does not match projection",
            expected=clock.filled,
            received=payload.before,
        )
    if payload.after != payload.before + payload.delta:
        raise InvariantViolation("clock_step", "clock advancement does not match delta")
    if not 0 <= payload.after <= clock.segments:
        raise InvariantViolation(
            "clock_bounds",
            "clock advancement leaves its segment range",
            after=payload.after,
            segments=clock.segments,
        )
    clock.filled = payload.after


def _inventory(holder: ProjectedEntity) -> dict[str, Any]:
    inventory = holder.state.get("inventory")
    if not isinstance(inventory, dict):
        inventory = {}
        holder.state["inventory"] = inventory
    return inventory


def _apply_item_transferred(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    item = projection.require_entity(payload.item_id)
    if item.kind is not EntityKind.ITEM:
        raise InvariantViolation(
            "not_an_item", "only item entities can be transferred", entity_id=item.id
        )
    holder = projection.require_entity(payload.to_entity_id)
    current = item.state.get("quantity")
    if not isinstance(current, int) or isinstance(current, bool) or current < payload.quantity:
        raise InvariantViolation(
            "insufficient_item_quantity",
            "item does not hold the requested quantity",
            item_id=item.id,
            requested=payload.quantity,
            available=current,
        )
    if payload.from_location_id is not None:
        if item.state.get("location_id") != payload.from_location_id:
            raise InvariantViolation(
                "stale_item_location",
                "item is not at the expected origin location",
                expected=item.state.get("location_id"),
                received=payload.from_location_id,
            )
    remaining = current - payload.quantity
    item.state["quantity"] = remaining
    item.state_version += 1
    inventory = _inventory(holder)
    entry = inventory.get(payload.item_slug)
    acquired = entry.get("quantity", 0) if isinstance(entry, dict) else 0
    inventory[payload.item_slug] = {
        "name": payload.item_name,
        "quantity": int(acquired) + payload.quantity,
    }
    holder.state_version += 1


def _apply_item_consumed(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    holder = projection.require_entity(payload.holder_id)
    inventory = _inventory(holder)
    entry = inventory.get(payload.item_slug)
    available = entry.get("quantity", 0) if isinstance(entry, dict) else 0
    if not isinstance(available, int) or available < payload.quantity:
        raise InvariantViolation(
            "insufficient_inventory",
            "holder does not carry the requested quantity",
            holder_id=holder.id,
            item_slug=payload.item_slug,
            requested=payload.quantity,
            available=available,
        )
    remaining = available - payload.quantity
    if remaining == 0:
        inventory.pop(payload.item_slug, None)
    elif isinstance(entry, dict):
        entry["quantity"] = remaining
    else:
        inventory[payload.item_slug] = {"name": payload.item_slug, "quantity": remaining}
    holder.state_version += 1


def _apply_item_given(projection: ProjectionState, envelope: EventEnvelope, payload: Any) -> None:
    holder = projection.require_entity(payload.holder_id)
    recipient = projection.require_entity(payload.recipient_id)
    inventory = _inventory(holder)
    entry = inventory.get(payload.item_slug)
    available = entry.get("quantity", 0) if isinstance(entry, dict) else 0
    if not isinstance(available, int) or isinstance(available, bool):
        available = 0
    if available < payload.quantity:
        raise InvariantViolation(
            "insufficient_inventory",
            "holder does not carry the requested quantity",
            holder_id=holder.id,
            item_slug=payload.item_slug,
            requested=payload.quantity,
            available=available,
        )
    remaining = available - payload.quantity
    if remaining == 0:
        inventory.pop(payload.item_slug, None)
    elif isinstance(entry, dict):
        entry["quantity"] = remaining
    recipient_inventory = _inventory(recipient)
    recipient_entry = recipient_inventory.get(payload.item_slug)
    carried = recipient_entry.get("quantity", 0) if isinstance(recipient_entry, dict) else 0
    recipient_inventory[payload.item_slug] = {
        "name": payload.item_name,
        "quantity": int(carried) + payload.quantity,
    }
    holder.state_version += 1
    recipient.state_version += 1


def _apply_entity_flag_set(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    if envelope.subject_id is None:
        raise InvariantViolation("missing_subject", "entity.flag_set requires a subject_id")
    entity = projection.require_entity(envelope.subject_id)
    flags = entity.state.get("flags")
    if not isinstance(flags, dict):
        flags = {}
        entity.state["flags"] = flags
    if flags.get(payload.key) != payload.before:
        raise InvariantViolation(
            "stale_flag",
            "entity flag before-value does not match projection",
            expected=flags.get(payload.key),
            received=payload.before,
        )
    flags[payload.key] = payload.after
    entity.state_version += 1


def _apply_campaign_ended(
    projection: ProjectionState, envelope: EventEnvelope, payload: Any
) -> None:
    if projection.ending is not None:
        raise InvariantViolation("campaign_already_ended", "the campaign already has an ending")
    projection.status = CampaignStatus.COMPLETED
    projection.ending = ProjectedEnding(
        outcome=payload.outcome,
        summary=payload.summary,
        event_id=envelope.event_id,
    )


def canonical_projection(projection: ProjectionState) -> dict[str, Any]:
    """Stable world-state payload used for replay/checkpoint hashing."""
    return {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": projection.campaign_id,
        "current_time": projection.current_time,
        "state_version": projection.state_version,
        "status": projection.status.value,
        "ending": (
            {
                "outcome": projection.ending.outcome,
                "summary": projection.ending.summary,
                "event_id": projection.ending.event_id,
            }
            if projection.ending is not None
            else None
        ),
        "entities": [
            {
                "id": entity.id,
                "kind": entity.kind.value,
                "slug": entity.slug,
                "display_name": entity.display_name,
                "static": entity.static,
                "state": entity.state,
                "state_version": entity.state_version,
                "retired_event_id": entity.retired_event_id,
            }
            for entity in sorted(projection.entities.values(), key=lambda item: item.id)
        ],
        "observations": [
            {
                "event_id": observation.event_id,
                "sequence": observation.sequence,
                "turn_id": observation.turn_id,
                "world_time": observation.world_time,
                "text": observation.text,
                "kind": observation.kind,
                "subject_ids": observation.subject_ids,
                "visibility": observation.visibility.value,
            }
            for observation in sorted(projection.observations, key=lambda item: item.sequence)
        ],
        "facts": [
            {
                "slug": fact.slug,
                "text": fact.text,
                "visibility": fact.visibility.value,
            }
            for fact in sorted(projection.facts.values(), key=lambda item: item.slug)
        ],
        "statements": [
            {
                "slug": statement.slug,
                "speaker_id": statement.speaker_id,
                "proposition": statement.proposition,
                "topic": statement.topic,
                "kind": statement.kind.value,
                "is_true": statement.is_true,
                "audience_ids": statement.audience_ids,
            }
            for statement in sorted(projection.statements.values(), key=lambda item: item.slug)
        ],
        "knowledge": [
            {
                "entity_id": knowledge.entity_id,
                "statement_slug": knowledge.statement_slug,
                "source": knowledge.source,
            }
            for knowledge in sorted(
                projection.knowledge.values(),
                key=lambda item: (item.entity_id, item.statement_slug),
            )
        ],
        "relationships": [
            {
                "from_id": relationship.from_id,
                "to_id": relationship.to_id,
                "dimension": relationship.dimension.value,
                "value": relationship.value,
            }
            for relationship in sorted(
                projection.relationships.values(),
                key=lambda item: (item.from_id, item.to_id, item.dimension.value),
            )
        ],
        "clocks": [
            {
                "slug": clock.slug,
                "name": clock.name,
                "segments": clock.segments,
                "filled": clock.filled,
                "trigger": clock.trigger,
                "owner_id": clock.owner_id,
                "visibility": clock.visibility.value,
            }
            for clock in sorted(projection.clocks.values(), key=lambda item: item.slug)
        ],
    }


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_projection(projection: ProjectionState) -> str:
    return hashlib.sha256(canonical_json(canonical_projection(projection)).encode()).hexdigest()


def public_state_view(projection: ProjectionState, *, actor_slug: str = "rowan") -> dict[str, Any]:
    """A deliberately small player-visible view.

    Entities marked ``gm_only`` in static data are omitted entirely; a
    visibility label is not enough, because the label itself can leak existence.
    """
    visible_entities = []
    for entity in sorted(projection.entities.values(), key=lambda item: item.slug):
        if entity.static.get("gm_only"):
            continue
        visible_entities.append(
            {
                "id": entity.id,
                "kind": entity.kind.value,
                "slug": entity.slug,
                "display_name": entity.display_name,
                "state": copy.deepcopy(entity.state),
                **_public_sheet(entity),
            }
        )
    return {
        "campaign_id": projection.campaign_id,
        "current_time": projection.current_time,
        "state_version": projection.state_version,
        "status": projection.status.value,
        "entities": visible_entities,
        "clocks": public_clocks_view(projection),
        "knowledge": player_knowledge_view(projection, actor_slug=actor_slug),
        "ending": (
            {
                "outcome": projection.ending.outcome,
                "summary": projection.ending.summary,
            }
            if projection.ending is not None
            else None
        ),
    }


def _public_sheet(entity: ProjectedEntity) -> dict[str, Any]:
    """Attributes, training, and template are safe player-facing rules data.

    Goals, plans, beliefs, and other static GM material are deliberately omitted.
    """
    sheet: dict[str, Any] = {}
    for key in ("template", "attributes", "training", "equipment", "abilities"):
        value = entity.static.get(key)
        if value is not None:
            sheet[key] = copy.deepcopy(value)
    return sheet


def public_clocks_view(projection: ProjectionState) -> list[dict[str, Any]]:
    """Clocks the player is allowed to see. GM-only clocks are omitted."""
    return [
        {
            "slug": clock.slug,
            "name": clock.name,
            "segments": clock.segments,
            "filled": clock.filled,
            "trigger": clock.trigger,
        }
        for clock in sorted(projection.clocks.values(), key=lambda item: item.slug)
        if clock.visibility is not Visibility.GM_ONLY
    ]


def player_knowledge_view(
    projection: ProjectionState, *, actor_slug: str = "rowan"
) -> list[dict[str, Any]]:
    """Statements a character knows.

    ``is_true`` is GM truth and is never exposed here. A statement is omitted
    when its speaker is GM-only so hidden entities cannot be inferred.
    """
    actor = projection.entity_by_slug(actor_slug)
    if actor is None:
        return []
    visible: list[dict[str, Any]] = []
    for knowledge in sorted(
        projection.knowledge.values(),
        key=lambda item: (item.statement_slug, item.entity_id),
    ):
        if knowledge.entity_id != actor.id:
            continue
        statement = projection.statements.get(knowledge.statement_slug)
        if statement is None:
            continue
        speaker = projection.entities.get(statement.speaker_id)
        if speaker is None or speaker.static.get("gm_only"):
            continue
        visible.append(
            {
                "statement_slug": statement.slug,
                "proposition": statement.proposition,
                "topic": statement.topic,
                "kind": statement.kind.value,
                "speaker_slug": speaker.slug,
                "speaker_name": speaker.display_name,
                "source": knowledge.source,
            }
        )
    return visible


def _gm_only_ids(projection: ProjectionState) -> set[str]:
    return {entity.id for entity in projection.entities.values() if entity.static.get("gm_only")}


def public_observations(
    projection: ProjectionState,
    *,
    after_sequence: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Player-visible journal entries, newest last.

    An observation is excluded when it is marked GM-only or when it refers to a
    GM-only entity. The second check is defense in depth: a visibility mistake
    must not leak a secret subject ID.
    """
    gm_only = _gm_only_ids(projection)
    visible: list[dict[str, Any]] = []
    for observation in sorted(projection.observations, key=lambda item: item.sequence):
        if observation.sequence <= after_sequence:
            continue
        if observation.visibility is Visibility.GM_ONLY:
            continue
        if gm_only.intersection(observation.subject_ids):
            continue
        visible.append(
            {
                "event_id": observation.event_id,
                "sequence": observation.sequence,
                "turn_id": observation.turn_id,
                "world_time": observation.world_time,
                "text": observation.text,
                "kind": observation.kind,
                "subject_ids": list(observation.subject_ids),
                "visibility": observation.visibility.value,
            }
        )
        if len(visible) >= limit:
            break
    return visible


def player_scene_view(projection: ProjectionState, *, actor_slug: str = "rowan") -> dict[str, Any]:
    """Focused view of the player character and their current location."""
    actor = projection.entity_by_slug(actor_slug)
    if actor is None:
        return {}
    location_id = actor.state.get("location_id")
    location = projection.entities.get(location_id) if isinstance(location_id, str) else None

    def _brief(entity: ProjectedEntity) -> dict[str, Any]:
        return {
            "id": entity.id,
            "kind": entity.kind.value,
            "slug": entity.slug,
            "display_name": entity.display_name,
            "state": copy.deepcopy(entity.state),
            **_public_sheet(entity),
        }

    present = []
    for entity in sorted(projection.entities.values(), key=lambda item: item.slug):
        if entity.static.get("gm_only"):
            continue
        if entity.id == actor.id:
            continue
        if location is not None and entity.state.get("location_id") == location.id:
            present.append(_brief(entity))

    return {
        "actor": _brief(actor),
        "location": _brief(location) if location is not None else None,
        "present": present,
    }
