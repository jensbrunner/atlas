"""Hard feasibility checks and command-to-event adjudication.

Every command is checked against the current projection before a draft event is
created. Invalid state cannot reach the event ledger.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from atlas.domain.commands import (
    AdjustResourceCommand,
    AdvanceTimeCommand,
    CreateEntityCommand,
    DomainCommand,
    MoveEntityCommand,
)
from atlas.domain.errors import InvariantViolation
from atlas.domain.events import (
    EntityCreatedPayload,
    EntityMovedPayload,
    EventDraft,
    EventType,
    ResourceChangedPayload,
    TimeAdvancedPayload,
    TurnCommittedPayload,
)
from atlas.domain.ids import new_id
from atlas.domain.models import EntityKind, ResourceName
from atlas.domain.projection import ProjectedEntity, ProjectionState
from atlas.domain.rules import DEFAULT_RESOURCE_BOUNDS

_MOVABLE_KINDS = {EntityKind.PLAYER_CHARACTER, EntityKind.NPC, EntityKind.ITEM}


@dataclass(slots=True)
class CommandApplication:
    projection: ProjectionState
    events: list[EventDraft]


def apply_commands(
    projection: ProjectionState,
    commands: Sequence[DomainCommand],
) -> CommandApplication:
    """Validate and apply commands to a clone of ``projection``.

    The caller receives proposed events; nothing is persisted here.
    """
    working = projection.clone()
    events: list[EventDraft] = []

    for command in commands:
        if isinstance(command, CreateEntityCommand):
            events.append(_create_entity(working, command))
        elif isinstance(command, AdjustResourceCommand):
            events.append(_adjust_resource(working, command))
        elif isinstance(command, MoveEntityCommand):
            events.append(_move_entity(working, command))
        elif isinstance(command, AdvanceTimeCommand):
            events.append(_advance_time(working, command))
        else:  # pragma: no cover - the discriminated union makes this unreachable
            raise InvariantViolation("unknown_command", f"unsupported command {command!r}")

    return CommandApplication(projection=working, events=events)


def build_turn_committed_draft(
    projection: ProjectionState,
    *,
    turn_id: str,
    ordinal: int,
) -> EventDraft:
    return EventDraft(
        event_type=EventType.TURN_COMMITTED,
        payload=TurnCommittedPayload(
            turn_id=turn_id,
            ordinal=ordinal,
            state_version=projection.state_version + 1,
        ),
        world_time=projection.current_time,
        subject_id=turn_id,
    )


def _create_entity(projection: ProjectionState, command: CreateEntityCommand) -> EventDraft:
    if projection.entity_by_slug(command.slug) is not None:
        raise InvariantViolation(
            "duplicate_slug",
            f"slug {command.slug!r} is already used in this campaign",
            slug=command.slug,
        )

    state = dict(command.state)
    if command.kind in {EntityKind.PLAYER_CHARACTER, EntityKind.NPC}:
        location_id = state.get("location_id")
        if not isinstance(location_id, str):
            raise InvariantViolation(
                "missing_location",
                "a living actor must have a physical location",
                slug=command.slug,
            )
        projection.require_location(location_id)

    for resource, value in state.items():
        try:
            resource_name = ResourceName(resource)
        except ValueError:
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            raise InvariantViolation(
                "resource_type",
                f"resource {resource!r} must be an integer",
                slug=command.slug,
            )
        low, high = _bounds(command.static, resource_name)
        if not low <= value <= high:
            raise InvariantViolation(
                "resource_bounds",
                f"initial {resource} value is outside bounds",
                slug=command.slug,
                value=value,
                min=low,
                max=high,
            )

    entity_id = new_id("ent")
    projection.entities[entity_id] = ProjectedEntity(
        id=entity_id,
        campaign_id=projection.campaign_id,
        kind=command.kind,
        slug=command.slug,
        display_name=command.display_name,
        static=dict(command.static),
        state=state,
        state_version=1,
    )
    return EventDraft(
        event_type=EventType.ENTITY_CREATED,
        payload=EntityCreatedPayload(
            kind=command.kind,
            slug=command.slug,
            display_name=command.display_name,
            static=command.static,
            state=state,
        ),
        world_time=projection.current_time,
        subject_id=entity_id,
    )


def _adjust_resource(projection: ProjectionState, command: AdjustResourceCommand) -> EventDraft:
    entity = projection.require_entity(command.entity_id)
    if entity.retired_event_id is not None:
        raise InvariantViolation(
            "entity_retired", "cannot change a retired entity", entity_id=entity.id
        )

    key = command.resource.value
    current = entity.state.get(key)
    if not isinstance(current, int) or isinstance(current, bool):
        raise InvariantViolation(
            "missing_resource",
            f"entity has no integer resource {key!r}",
            entity_id=entity.id,
            resource=key,
        )

    low, high = _bounds(entity.static, command.resource)
    after = current + command.delta
    if not low <= after <= high:
        raise InvariantViolation(
            "resource_bounds",
            f"{key} would move outside [{low}, {high}]",
            entity_id=entity.id,
            resource=key,
            before=current,
            after=after,
            min=low,
            max=high,
        )

    entity.state[key] = after
    entity.state_version += 1
    return EventDraft(
        event_type=EventType.RESOURCE_CHANGED,
        payload=ResourceChangedPayload(
            resource=command.resource,
            delta=command.delta,
            before=current,
            after=after,
            min=low,
            max=high,
            reason=command.reason,
        ),
        world_time=projection.current_time,
        actor_id=entity.id,
        subject_id=entity.id,
    )


def _move_entity(projection: ProjectionState, command: MoveEntityCommand) -> EventDraft:
    entity = projection.require_entity(command.entity_id)
    if entity.retired_event_id is not None:
        raise InvariantViolation(
            "entity_retired", "cannot move a retired entity", entity_id=entity.id
        )
    if entity.kind not in _MOVABLE_KINDS:
        raise InvariantViolation(
            "not_movable",
            f"an entity of kind {entity.kind.value!r} cannot be moved",
            entity_id=entity.id,
        )

    projection.require_location(command.to_location_id)
    current = entity.state.get("location_id")
    if not isinstance(current, str):
        raise InvariantViolation(
            "missing_location", "entity has no current location", entity_id=entity.id
        )
    if current == command.to_location_id:
        raise InvariantViolation(
            "same_location",
            "entity is already at the requested location",
            entity_id=entity.id,
            location_id=current,
        )

    entity.state["location_id"] = command.to_location_id
    entity.state_version += 1
    return EventDraft(
        event_type=EventType.ENTITY_MOVED,
        payload=EntityMovedPayload(
            from_location_id=current,
            to_location_id=command.to_location_id,
            reason=command.reason,
        ),
        world_time=projection.current_time,
        actor_id=entity.id,
        subject_id=entity.id,
    )


def _advance_time(projection: ProjectionState, command: AdvanceTimeCommand) -> EventDraft:
    before = projection.current_time
    after = before + command.minutes
    projection.current_time = after
    return EventDraft(
        event_type=EventType.TIME_ADVANCED,
        payload=TimeAdvancedPayload(
            minutes=command.minutes,
            before=before,
            after=after,
            reason=command.reason,
        ),
        world_time=after,
        subject_id=None,
    )


def _bounds(static: dict[str, Any], resource: ResourceName) -> tuple[int, int]:
    return resource_bounds(static, resource)


def resource_bounds(static: dict[str, Any], resource: ResourceName) -> tuple[int, int]:
    """Resolve configured resource bounds, falling back to core defaults."""
    configured = static.get("resource_bounds", {})
    if isinstance(configured, dict) and resource.value in configured:
        raw = configured[resource.value]
        if isinstance(raw, dict):
            low, high = raw.get("min"), raw.get("max")
        elif isinstance(raw, (list, tuple)) and len(raw) == 2:
            low, high = raw
        else:
            raise InvariantViolation(
                "invalid_bounds",
                f"invalid resource bounds for {resource.value!r}",
            )
        if (
            not isinstance(low, int)
            or isinstance(low, bool)
            or not isinstance(high, int)
            or isinstance(high, bool)
            or low > high
        ):
            raise InvariantViolation(
                "invalid_bounds",
                f"invalid resource bounds for {resource.value!r}",
            )
        return low, high
    return DEFAULT_RESOURCE_BOUNDS[resource]
