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
    AdvanceClockCommand,
    AdvanceTimeCommand,
    ChangeRelationshipCommand,
    ConsumeItemCommand,
    CreateClockCommand,
    CreateEntityCommand,
    CreateFactCommand,
    DomainCommand,
    EndCampaignCommand,
    GiveItemCommand,
    LearnStatementCommand,
    MoveEntityCommand,
    RecordStatementCommand,
    SetEntityFlagCommand,
    TransferItemCommand,
)
from atlas.domain.errors import InvariantViolation
from atlas.domain.events import (
    CampaignEndedPayload,
    ClockAdvancedPayload,
    ClockCreatedPayload,
    EntityCreatedPayload,
    EntityFlagSetPayload,
    EntityMovedPayload,
    EventDraft,
    EventType,
    FactRecordedPayload,
    ItemConsumedPayload,
    ItemGivenPayload,
    ItemTransferredPayload,
    KnowledgeRecordedPayload,
    RelationshipChangedPayload,
    ResourceChangedPayload,
    StatementRecordedPayload,
    TimeAdvancedPayload,
    TurnCommittedPayload,
)
from atlas.domain.ids import new_id
from atlas.domain.models import (
    CampaignStatus,
    EntityKind,
    ResourceName,
    Visibility,
)
from atlas.domain.projection import (
    ProjectedClock,
    ProjectedEnding,
    ProjectedEntity,
    ProjectedFact,
    ProjectedKnowledge,
    ProjectedRelationship,
    ProjectedStatement,
    ProjectionState,
)
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

    if commands and working.ending is not None:
        raise InvariantViolation(
            "campaign_ended",
            "no commands may be applied after the campaign has ended",
        )

    for command in commands:
        draft: EventDraft | None
        if isinstance(command, CreateEntityCommand):
            draft = _create_entity(working, command)
        elif isinstance(command, AdjustResourceCommand):
            draft = _adjust_resource(working, command)
        elif isinstance(command, MoveEntityCommand):
            draft = _move_entity(working, command)
        elif isinstance(command, AdvanceTimeCommand):
            draft = _advance_time(working, command)
        elif isinstance(command, CreateFactCommand):
            draft = _create_fact(working, command)
        elif isinstance(command, RecordStatementCommand):
            draft = _record_statement(working, command)
        elif isinstance(command, LearnStatementCommand):
            draft = _learn_statement(working, command)
        elif isinstance(command, ChangeRelationshipCommand):
            draft = _change_relationship(working, command)
        elif isinstance(command, CreateClockCommand):
            draft = _create_clock(working, command)
        elif isinstance(command, AdvanceClockCommand):
            draft = _advance_clock(working, command)
        elif isinstance(command, TransferItemCommand):
            draft = _transfer_item(working, command)
        elif isinstance(command, GiveItemCommand):
            draft = _give_item(working, command)
        elif isinstance(command, ConsumeItemCommand):
            draft = _consume_item(working, command)
        elif isinstance(command, SetEntityFlagCommand):
            draft = _set_entity_flag(working, command)
        elif isinstance(command, EndCampaignCommand):
            draft = _end_campaign(working, command)
        else:  # pragma: no cover - the discriminated union makes this unreachable
            raise InvariantViolation("unknown_command", f"unsupported command {command!r}")
        if draft is not None:
            events.append(draft)

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


def _create_fact(projection: ProjectionState, command: CreateFactCommand) -> EventDraft:
    if command.fact_slug in projection.facts:
        raise InvariantViolation(
            "duplicate_fact",
            f"fact {command.fact_slug!r} is already recorded",
            slug=command.fact_slug,
        )
    projection.facts[command.fact_slug] = ProjectedFact(
        slug=command.fact_slug,
        text=command.text,
        visibility=command.visibility,
        event_id="",
    )
    return EventDraft(
        event_type=EventType.FACT_RECORDED,
        payload=FactRecordedPayload(
            fact_slug=command.fact_slug,
            text=command.text,
            visibility=command.visibility,
        ),
        world_time=projection.current_time,
        subject_id=None,
    )


def _record_statement(projection: ProjectionState, command: RecordStatementCommand) -> EventDraft:
    if command.statement_slug in projection.statements:
        raise InvariantViolation(
            "duplicate_statement",
            f"statement {command.statement_slug!r} is already recorded",
            slug=command.statement_slug,
        )
    projection.require_entity(command.speaker_id)
    for audience_id in command.audience_ids:
        projection.require_entity(audience_id)
    projection.statements[command.statement_slug] = ProjectedStatement(
        slug=command.statement_slug,
        speaker_id=command.speaker_id,
        proposition=command.proposition,
        topic=command.topic,
        kind=command.kind,
        is_true=command.is_true,
        audience_ids=list(command.audience_ids),
        event_id="",
    )
    projection.knowledge[(command.speaker_id, command.statement_slug)] = ProjectedKnowledge(
        entity_id=command.speaker_id,
        statement_slug=command.statement_slug,
        source="statement",
        event_id="",
    )
    return EventDraft(
        event_type=EventType.STATEMENT_RECORDED,
        payload=StatementRecordedPayload(
            statement_slug=command.statement_slug,
            speaker_id=command.speaker_id,
            proposition=command.proposition,
            topic=command.topic,
            kind=command.kind,
            is_true=command.is_true,
            audience_ids=command.audience_ids,
        ),
        world_time=projection.current_time,
        actor_id=command.speaker_id,
        subject_id=command.speaker_id,
    )


def _learn_statement(
    projection: ProjectionState, command: LearnStatementCommand
) -> EventDraft | None:
    projection.require_entity(command.entity_id)
    if command.statement_slug not in projection.statements:
        raise InvariantViolation(
            "unknown_statement",
            f"statement {command.statement_slug!r} does not exist",
            slug=command.statement_slug,
        )
    key = (command.entity_id, command.statement_slug)
    if key in projection.knowledge:
        return None
    projection.knowledge[key] = ProjectedKnowledge(
        entity_id=command.entity_id,
        statement_slug=command.statement_slug,
        source=command.source,
        event_id="",
    )
    return EventDraft(
        event_type=EventType.KNOWLEDGE_RECORDED,
        payload=KnowledgeRecordedPayload(
            entity_id=command.entity_id,
            statement_slug=command.statement_slug,
            source=command.source,
        ),
        world_time=projection.current_time,
        subject_id=command.entity_id,
    )


def _change_relationship(
    projection: ProjectionState, command: ChangeRelationshipCommand
) -> EventDraft:
    projection.require_entity(command.from_id)
    projection.require_entity(command.to_id)
    before = projection.relationship_value(command.from_id, command.to_id, command.dimension)
    after = before + command.delta
    if not -5 <= after <= 5:
        raise InvariantViolation(
            "relationship_bounds",
            "relationship would leave the supported range",
            before=before,
            after=after,
        )
    projection.relationships[(command.from_id, command.to_id, command.dimension)] = (
        ProjectedRelationship(
            from_id=command.from_id,
            to_id=command.to_id,
            dimension=command.dimension,
            value=after,
            updated_event_id="",
        )
    )
    return EventDraft(
        event_type=EventType.RELATIONSHIP_CHANGED,
        payload=RelationshipChangedPayload(
            from_id=command.from_id,
            to_id=command.to_id,
            dimension=command.dimension,
            before=before,
            after=after,
        ),
        world_time=projection.current_time,
        subject_id=command.from_id,
    )


def _create_clock(projection: ProjectionState, command: CreateClockCommand) -> EventDraft:
    if command.clock_slug in projection.clocks:
        raise InvariantViolation(
            "duplicate_clock",
            f"clock {command.clock_slug!r} already exists",
            slug=command.clock_slug,
        )
    if command.filled > command.segments:
        raise InvariantViolation(
            "clock_bounds",
            "initial clock fill must be within its segment count",
            filled=command.filled,
            segments=command.segments,
        )
    if command.owner_id is not None:
        projection.require_entity(command.owner_id)
    projection.clocks[command.clock_slug] = ProjectedClock(
        slug=command.clock_slug,
        name=command.name,
        segments=command.segments,
        filled=command.filled,
        trigger=command.trigger,
        owner_id=command.owner_id,
        visibility=command.visibility,
        created_event_id="",
    )
    return EventDraft(
        event_type=EventType.CLOCK_CREATED,
        payload=ClockCreatedPayload(
            clock_slug=command.clock_slug,
            name=command.name,
            segments=command.segments,
            filled=command.filled,
            trigger=command.trigger,
            owner_id=command.owner_id,
            visibility=command.visibility,
        ),
        world_time=projection.current_time,
        subject_id=command.owner_id,
    )


def _advance_clock(projection: ProjectionState, command: AdvanceClockCommand) -> EventDraft:
    clock = projection.clocks.get(command.clock_slug)
    if clock is None:
        raise InvariantViolation(
            "unknown_clock",
            f"clock {command.clock_slug!r} does not exist",
            slug=command.clock_slug,
        )
    before = clock.filled
    after = before + command.delta
    if not 0 <= after <= clock.segments:
        raise InvariantViolation(
            "clock_bounds",
            "clock would leave its segment range",
            before=before,
            after=after,
            segments=clock.segments,
        )
    clock.filled = after
    return EventDraft(
        event_type=EventType.CLOCK_ADVANCED,
        payload=ClockAdvancedPayload(
            clock_slug=command.clock_slug,
            delta=command.delta,
            before=before,
            after=after,
            reason=command.reason,
        ),
        world_time=projection.current_time,
        subject_id=clock.owner_id,
    )


def _inventory(holder: ProjectedEntity) -> dict[str, Any]:
    inventory = holder.state.get("inventory")
    if not isinstance(inventory, dict):
        inventory = {}
        holder.state["inventory"] = inventory
    return inventory


def _transfer_item(projection: ProjectionState, command: TransferItemCommand) -> EventDraft:
    item = projection.require_entity(command.item_id)
    if item.kind is not EntityKind.ITEM:
        raise InvariantViolation(
            "not_an_item", "only item entities can be transferred", entity_id=item.id
        )
    holder = projection.require_entity(command.to_entity_id)
    if holder.kind not in {EntityKind.PLAYER_CHARACTER, EntityKind.NPC}:
        raise InvariantViolation(
            "invalid_item_holder",
            "items can only be transferred to a character or NPC",
            entity_id=holder.id,
        )
    available = item.state.get("quantity")
    if not isinstance(available, int) or isinstance(available, bool):
        raise InvariantViolation(
            "missing_item_quantity", "item has no integer quantity", item_id=item.id
        )
    if available < command.quantity:
        raise InvariantViolation(
            "insufficient_item_quantity",
            "item does not hold the requested quantity",
            item_id=item.id,
            requested=command.quantity,
            available=available,
        )
    from_location = item.state.get("location_id")
    if isinstance(from_location, str) and holder.state.get("location_id") != from_location:
        raise InvariantViolation(
            "item_not_reachable",
            "item and holder are not in the same location",
            item_location=from_location,
            holder_location=holder.state.get("location_id"),
        )
    item.state["quantity"] = available - command.quantity
    item.state_version += 1
    inventory = _inventory(holder)
    entry = inventory.get(item.slug)
    carried = entry.get("quantity", 0) if isinstance(entry, dict) else 0
    inventory[item.slug] = {
        "name": item.display_name,
        "quantity": int(carried) + command.quantity,
    }
    holder.state_version += 1
    return EventDraft(
        event_type=EventType.ITEM_TRANSFERRED,
        payload=ItemTransferredPayload(
            item_id=item.id,
            item_slug=item.slug,
            item_name=item.display_name,
            quantity=command.quantity,
            from_location_id=from_location if isinstance(from_location, str) else None,
            to_entity_id=holder.id,
        ),
        world_time=projection.current_time,
        actor_id=holder.id,
        subject_id=item.id,
    )


def _give_item(projection: ProjectionState, command: GiveItemCommand) -> EventDraft:
    holder = projection.require_entity(command.holder_id)
    recipient = projection.require_entity(command.recipient_id)
    if holder.id == recipient.id:
        raise InvariantViolation("self_transfer", "a character cannot give an item to itself")
    if recipient.kind not in {EntityKind.PLAYER_CHARACTER, EntityKind.NPC}:
        raise InvariantViolation(
            "invalid_item_holder",
            "items can only be given to a character or NPC",
            entity_id=recipient.id,
        )
    inventory = _inventory(holder)
    entry = inventory.get(command.item_slug)
    available = entry.get("quantity", 0) if isinstance(entry, dict) else 0
    if not isinstance(available, int) or isinstance(available, bool):
        available = 0
    if available < command.quantity:
        raise InvariantViolation(
            "insufficient_inventory",
            "holder does not carry the requested quantity",
            holder_id=holder.id,
            item_slug=command.item_slug,
            requested=command.quantity,
            available=available,
        )
    item_name = (
        str(entry.get("name", command.item_slug)) if isinstance(entry, dict) else command.item_slug
    )
    remaining = available - command.quantity
    if remaining == 0:
        inventory.pop(command.item_slug, None)
    elif isinstance(entry, dict):
        entry["quantity"] = remaining
    recipient_inventory = _inventory(recipient)
    recipient_entry = recipient_inventory.get(command.item_slug)
    carried = recipient_entry.get("quantity", 0) if isinstance(recipient_entry, dict) else 0
    recipient_inventory[command.item_slug] = {
        "name": item_name,
        "quantity": int(carried) + command.quantity,
    }
    holder.state_version += 1
    recipient.state_version += 1
    return EventDraft(
        event_type=EventType.ITEM_GIVEN,
        payload=ItemGivenPayload(
            holder_id=holder.id,
            recipient_id=recipient.id,
            item_slug=command.item_slug,
            item_name=item_name,
            quantity=command.quantity,
        ),
        world_time=projection.current_time,
        actor_id=holder.id,
        subject_id=recipient.id,
    )


def _consume_item(projection: ProjectionState, command: ConsumeItemCommand) -> EventDraft:
    holder = projection.require_entity(command.holder_id)
    inventory = _inventory(holder)
    entry = inventory.get(command.item_slug)
    available = entry.get("quantity", 0) if isinstance(entry, dict) else 0
    if not isinstance(available, int) or isinstance(available, bool):
        available = 0
    if available < command.quantity:
        raise InvariantViolation(
            "insufficient_inventory",
            "holder does not carry the requested quantity",
            holder_id=holder.id,
            item_slug=command.item_slug,
            requested=command.quantity,
            available=available,
        )
    remaining = available - command.quantity
    if remaining == 0:
        inventory.pop(command.item_slug, None)
    elif isinstance(entry, dict):
        entry["quantity"] = remaining
    else:
        inventory[command.item_slug] = {"name": command.item_slug, "quantity": remaining}
    holder.state_version += 1
    return EventDraft(
        event_type=EventType.ITEM_CONSUMED,
        payload=ItemConsumedPayload(
            holder_id=holder.id,
            item_slug=command.item_slug,
            quantity=command.quantity,
        ),
        world_time=projection.current_time,
        actor_id=holder.id,
        subject_id=holder.id,
    )


def _set_entity_flag(projection: ProjectionState, command: SetEntityFlagCommand) -> EventDraft:
    entity = projection.require_entity(command.entity_id)
    flags = entity.state.get("flags")
    if not isinstance(flags, dict):
        flags = {}
        entity.state["flags"] = flags
    before = flags.get(command.key)
    flags[command.key] = command.value
    entity.state_version += 1
    return EventDraft(
        event_type=EventType.ENTITY_FLAG_SET,
        payload=EntityFlagSetPayload(
            key=command.key,
            before=before,
            after=command.value,
        ),
        world_time=projection.current_time,
        actor_id=entity.id,
        subject_id=entity.id,
    )


def _end_campaign(projection: ProjectionState, command: EndCampaignCommand) -> EventDraft:
    if projection.ending is not None:
        raise InvariantViolation("campaign_already_ended", "the campaign already has an ending")
    projection.status = CampaignStatus.COMPLETED
    projection.ending = ProjectedEnding(
        outcome=command.outcome,
        summary=command.summary,
        event_id="",
    )
    return EventDraft(
        event_type=EventType.CAMPAIGN_ENDED,
        payload=CampaignEndedPayload(
            outcome=command.outcome,
            summary=command.summary,
        ),
        world_time=projection.current_time,
        subject_id=None,
        visibility=Visibility.PUBLIC,
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
