"""In-memory world-state projection derived solely from committed events."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from atlas.domain.errors import InvariantViolation
from atlas.domain.events import EventEnvelope, EventType, parse_event_payload
from atlas.domain.models import EntityKind, Visibility

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
class ProjectionState:
    campaign_id: str
    current_time: int = 0
    state_version: int = 0
    last_event_seq: int = 0
    entities: dict[str, ProjectedEntity] = field(default_factory=dict)
    observations: list[ProjectedObservation] = field(default_factory=list)

    def clone(self) -> ProjectionState:
        return copy.deepcopy(self)

    def entity_by_slug(self, slug: str) -> ProjectedEntity | None:
        for entity in self.entities.values():
            if entity.slug == slug:
                return entity
        return None

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


def canonical_projection(projection: ProjectionState) -> dict[str, Any]:
    """Stable world-state payload used for replay/checkpoint hashing."""
    return {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": projection.campaign_id,
        "current_time": projection.current_time,
        "state_version": projection.state_version,
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
    }


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_projection(projection: ProjectionState) -> str:
    return hashlib.sha256(canonical_json(canonical_projection(projection)).encode()).hexdigest()


def public_state_view(projection: ProjectionState) -> dict[str, Any]:
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
            }
        )
    return {
        "campaign_id": projection.campaign_id,
        "current_time": projection.current_time,
        "state_version": projection.state_version,
        "entities": visible_entities,
    }


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
        }

    present = []
    for entity in sorted(projection.entities.values(), key=lambda item: item.slug):
        if entity.static.get("gm_only"):
            continue
        if entity.id == actor.id:
            continue
        if location is not None and (
            entity.id == location.id or entity.state.get("location_id") == location.id
        ):
            present.append(_brief(entity))

    return {
        "actor": _brief(actor),
        "location": _brief(location) if location is not None else None,
        "present": present,
    }
