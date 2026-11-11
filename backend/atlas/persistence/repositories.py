"""Repository operations over canonical rows and derived projections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.domain.errors import InvariantViolation, NotFoundError
from atlas.domain.events import (
    EventDraft,
    EventEnvelope,
    EventType,
    Provenance,
    SceneObservedPayload,
    parse_event_payload,
)
from atlas.domain.ids import new_id
from atlas.domain.models import (
    Campaign,
    CampaignSettings,
    CampaignStatus,
    Entity,
    EntityKind,
    EntityState,
    RelationshipDimension,
    StatementKind,
    Visibility,
)
from atlas.domain.projection import (
    ProjectedClock,
    ProjectedEnding,
    ProjectedEntity,
    ProjectedFact,
    ProjectedKnowledge,
    ProjectedObservation,
    ProjectedRelationship,
    ProjectedStatement,
    ProjectionState,
    apply_event,
    canonical_projection,
    hash_projection,
)
from atlas.persistence.orm import (
    CampaignRow,
    CheckpointRow,
    ClockRow,
    EntityRow,
    EntityStateRow,
    EventRow,
    FactRow,
    KnowledgeRow,
    ObservationRow,
    RelationshipRow,
    RollRow,
    StatementRow,
    TurnRow,
    utcnow,
)


def create_campaign(
    session: Session,
    *,
    title: str,
    seed: int,
    settings: CampaignSettings | None = None,
    rules_version: str = "0.1",
) -> CampaignRow:
    row = CampaignRow(
        id=new_id("cmp"),
        title=title,
        rules_version=rules_version,
        status=CampaignStatus.ACTIVE.value,
        state_version=0,
        current_time=0,
        seed=seed,
        settings_json=(settings or CampaignSettings()).model_dump(mode="json"),
    )
    session.add(row)
    session.flush()
    return row


def get_campaign(session: Session, campaign_id: str) -> CampaignRow:
    row = session.get(CampaignRow, campaign_id)
    if row is None:
        raise NotFoundError(f"campaign {campaign_id!r} does not exist", campaign_id=campaign_id)
    return row


def list_campaigns(session: Session) -> list[CampaignRow]:
    return list(session.scalars(select(CampaignRow).order_by(CampaignRow.created_at.desc())))


def campaign_model(row: CampaignRow) -> Campaign:
    return Campaign(
        id=row.id,
        title=row.title,
        rules_version=row.rules_version,
        status=CampaignStatus(row.status),
        state_version=row.state_version,
        current_time=row.current_time,
        seed=row.seed,
        settings=CampaignSettings.model_validate(row.settings_json),
        ending=dict(row.ending_json) if isinstance(row.ending_json, dict) else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def entity_model(entity: ProjectedEntity) -> Entity:
    return Entity(
        id=entity.id,
        campaign_id=entity.campaign_id,
        kind=entity.kind,
        slug=entity.slug,
        display_name=entity.display_name,
        static=entity.static,
        created_event_id=entity.created_event_id,
        retired_event_id=entity.retired_event_id,
    )


def entity_state_model(entity: ProjectedEntity) -> EntityState:
    return EntityState(
        entity_id=entity.id,
        campaign_id=entity.campaign_id,
        version=entity.state_version,
        state=entity.state,
    )


def load_projection(session: Session, campaign_id: str) -> ProjectionState:
    """Load the current event-derived projection from relational rows."""
    campaign = get_campaign(session, campaign_id)
    last_seq = session.scalar(
        select(func.max(EventRow.seq)).where(EventRow.campaign_id == campaign_id)
    )
    rows = session.execute(
        select(EntityRow, EntityStateRow)
        .join(EntityStateRow, EntityStateRow.entity_id == EntityRow.id)
        .where(EntityRow.campaign_id == campaign_id)
    ).all()

    projection = ProjectionState(
        campaign_id=campaign_id,
        current_time=campaign.current_time,
        state_version=campaign.state_version,
        last_event_seq=int(last_seq or 0),
        status=CampaignStatus(campaign.status),
    )
    if isinstance(campaign.ending_json, dict):
        projection.ending = ProjectedEnding(
            outcome=str(campaign.ending_json.get("outcome", "")),
            summary=str(campaign.ending_json.get("summary", "")),
            event_id=str(campaign.ending_json.get("event_id", "")),
        )
    for entity_row, state_row in rows:
        projection.entities[entity_row.id] = ProjectedEntity(
            id=entity_row.id,
            campaign_id=entity_row.campaign_id,
            kind=EntityKind(entity_row.kind),
            slug=entity_row.slug,
            display_name=entity_row.display_name,
            static=dict(entity_row.static_json),
            state=dict(state_row.state_json),
            state_version=state_row.version,
            created_event_id=entity_row.created_event_id,
            retired_event_id=entity_row.retired_event_id,
        )

    observation_rows = session.scalars(
        select(ObservationRow)
        .where(ObservationRow.campaign_id == campaign_id)
        .order_by(ObservationRow.seq)
    )
    for row in observation_rows:
        projection.observations.append(
            ProjectedObservation(
                event_id=row.id,
                campaign_id=row.campaign_id,
                sequence=row.seq,
                turn_id=row.turn_id,
                world_time=row.occurred_at_world,
                text=row.text,
                kind=row.kind,
                subject_ids=list(row.subject_ids_json),
                visibility=Visibility(row.visibility),
            )
        )

    for fact_row in session.scalars(select(FactRow).where(FactRow.campaign_id == campaign_id)):
        projection.facts[fact_row.slug] = ProjectedFact(
            slug=fact_row.slug,
            text=fact_row.text,
            visibility=Visibility(fact_row.visibility),
            event_id=fact_row.id,
        )

    for statement_row in session.scalars(
        select(StatementRow).where(StatementRow.campaign_id == campaign_id)
    ):
        projection.statements[statement_row.slug] = ProjectedStatement(
            slug=statement_row.slug,
            speaker_id=statement_row.speaker_id,
            proposition=statement_row.proposition,
            topic=statement_row.topic,
            kind=StatementKind(statement_row.kind),
            is_true=statement_row.is_true,
            audience_ids=list(statement_row.audience_ids_json),
            event_id=statement_row.id,
        )

    for knowledge_row in session.scalars(
        select(KnowledgeRow).where(KnowledgeRow.campaign_id == campaign_id)
    ):
        projection.knowledge[(knowledge_row.entity_id, knowledge_row.statement_slug)] = (
            ProjectedKnowledge(
                entity_id=knowledge_row.entity_id,
                statement_slug=knowledge_row.statement_slug,
                source=knowledge_row.source,
                event_id=knowledge_row.event_id,
            )
        )

    for relationship_row in session.scalars(
        select(RelationshipRow).where(RelationshipRow.campaign_id == campaign_id)
    ):
        dimension = RelationshipDimension(relationship_row.dimension)
        projection.relationships[(relationship_row.from_id, relationship_row.to_id, dimension)] = (
            ProjectedRelationship(
                from_id=relationship_row.from_id,
                to_id=relationship_row.to_id,
                dimension=dimension,
                value=relationship_row.value,
                updated_event_id=relationship_row.event_id,
            )
        )

    for clock_row in session.scalars(select(ClockRow).where(ClockRow.campaign_id == campaign_id)):
        projection.clocks[clock_row.slug] = ProjectedClock(
            slug=clock_row.slug,
            name=clock_row.name,
            segments=clock_row.segments,
            filled=clock_row.filled,
            trigger=clock_row.trigger,
            owner_id=clock_row.owner_id,
            visibility=Visibility(clock_row.visibility),
            created_event_id=clock_row.created_event_id,
        )
    return projection


def load_events(session: Session, campaign_id: str) -> list[EventEnvelope]:
    rows = session.scalars(
        select(EventRow).where(EventRow.campaign_id == campaign_id).order_by(EventRow.seq)
    )
    envelopes: list[EventEnvelope] = []
    for row in rows:
        envelopes.append(
            EventEnvelope(
                schema_version=row.schema_version,
                event_id=row.id,
                campaign_id=row.campaign_id,
                turn_id=row.turn_id,
                sequence=row.seq,
                event_type=row.type,
                world_time=row.occurred_at_world,
                actor_id=row.actor_id,
                subject_id=row.subject_id,
                cause_event_ids=list(row.cause_event_ids_json),
                payload=dict(row.payload_json),
                visibility=row.visibility,
                provenance=row.provenance_json,
            )
        )
    return envelopes


def replay_projection(session: Session, campaign_id: str) -> ProjectionState:
    projection = ProjectionState(campaign_id=campaign_id)
    for envelope in load_events(session, campaign_id):
        apply_event(projection, envelope)
    return projection


@dataclass(frozen=True, slots=True)
class ReplayReport:
    campaign_id: str
    matched: bool
    live_hash: str
    replay_hash: str
    event_seq: int


def verify_replay(session: Session, campaign_id: str) -> ReplayReport:
    live = load_projection(session, campaign_id)
    replayed = replay_projection(session, campaign_id)
    live_hash = hash_projection(live)
    replay_hash = hash_projection(replayed)
    return ReplayReport(
        campaign_id=campaign_id,
        matched=live_hash == replay_hash,
        live_hash=live_hash,
        replay_hash=replay_hash,
        event_seq=live.last_event_seq,
    )


def next_event_sequence(session: Session, campaign_id: str) -> int:
    current = session.scalar(
        select(func.max(EventRow.seq)).where(EventRow.campaign_id == campaign_id)
    )
    return int(current or 0) + 1


def commit_event_batch(
    session: Session,
    campaign: CampaignRow,
    drafts: list[EventDraft],
    *,
    turn_id: str | None,
    authority: str = "rules_engine",
    rules_version: str = "0.1",
    note: str | None = None,
) -> tuple[list[EventEnvelope], ProjectionState]:
    """Append validated drafts and update projections in the caller's transaction.

    The caller must hold the transaction and must have checked the campaign
    version. Sequence uniqueness is enforced by the database.
    """
    projection = load_projection(session, campaign.id)
    start_seq = next_event_sequence(session, campaign.id)
    provenance = Provenance(authority=authority, rules_version=rules_version, note=note)
    envelopes: list[EventEnvelope] = []
    changed_entity_ids: set[str] = set()

    for offset, draft in enumerate(drafts):
        envelope = draft.to_envelope(
            event_id=new_id("evt"),
            campaign_id=campaign.id,
            sequence=start_seq + offset,
            turn_id=turn_id,
            provenance=provenance,
        )
        apply_event(projection, envelope)
        envelopes.append(envelope)
        session.add(_event_row(envelope))
        if envelope.event_type is EventType.SCENE_OBSERVED:
            session.add(_observation_row(envelope))
        if draft.subject_id is not None and draft.subject_id in projection.entities:
            changed_entity_ids.add(draft.subject_id)
        if draft.actor_id is not None and draft.actor_id in projection.entities:
            changed_entity_ids.add(draft.actor_id)

    campaign.current_time = projection.current_time
    campaign.state_version = projection.state_version
    campaign.status = projection.status.value
    campaign.ending_json = (
        {
            "outcome": projection.ending.outcome,
            "summary": projection.ending.summary,
            "event_id": projection.ending.event_id,
        }
        if projection.ending is not None
        else None
    )
    campaign.updated_at = utcnow()
    _write_entity_rows(session, projection, changed_entity_ids)
    _sync_world_rows(session, projection)
    session.flush()
    return envelopes, projection


def _observation_row(envelope: EventEnvelope) -> ObservationRow:
    payload = parse_event_payload(envelope.event_type, envelope.payload)
    if not isinstance(payload, SceneObservedPayload):  # pragma: no cover - guarded by event type
        raise InvariantViolation("observation_payload", "unexpected observation payload")
    return ObservationRow(
        id=envelope.event_id,
        campaign_id=envelope.campaign_id,
        turn_id=envelope.turn_id,
        seq=envelope.sequence,
        text=payload.text,
        kind=payload.kind,
        subject_ids_json=list(payload.subject_ids),
        visibility=envelope.visibility.value,
        occurred_at_world=envelope.world_time,
    )


def _event_row(envelope: EventEnvelope) -> EventRow:
    return EventRow(
        id=envelope.event_id,
        campaign_id=envelope.campaign_id,
        turn_id=envelope.turn_id,
        seq=envelope.sequence,
        type=envelope.event_type.value,
        actor_id=envelope.actor_id,
        subject_id=envelope.subject_id,
        payload_json=envelope.payload,
        inverse_json=None,
        occurred_at_world=envelope.world_time,
        schema_version=envelope.schema_version,
        provenance_json=envelope.provenance.model_dump(mode="json"),
        visibility=envelope.visibility.value,
        cause_event_ids_json=envelope.cause_event_ids,
    )


def _write_entity_rows(session: Session, projection: ProjectionState, entity_ids: set[str]) -> None:
    for entity_id in sorted(entity_ids):
        projected = projection.entities.get(entity_id)
        if projected is None:
            raise InvariantViolation(
                "projection_missing_entity",
                f"event referenced missing entity {entity_id!r}",
            )
        row = session.get(EntityRow, entity_id)
        if row is None:
            row = EntityRow(
                id=projected.id,
                campaign_id=projected.campaign_id,
                kind=projected.kind.value,
                slug=projected.slug,
                display_name=projected.display_name,
                static_json=projected.static,
                created_event_id=projected.created_event_id,
                retired_event_id=projected.retired_event_id,
            )
            session.add(row)
        else:
            row.display_name = projected.display_name
            row.static_json = projected.static
            row.retired_event_id = projected.retired_event_id

        state_row = session.get(EntityStateRow, entity_id)
        if state_row is None:
            state_row = EntityStateRow(
                entity_id=entity_id,
                campaign_id=projected.campaign_id,
                version=projected.state_version,
                state_json=projected.state,
            )
            session.add(state_row)
        else:
            state_row.version = projected.state_version
            state_row.state_json = projected.state


def _sync_world_rows(session: Session, projection: ProjectionState) -> None:
    for fact in projection.facts.values():
        fact_row = session.scalar(
            select(FactRow).where(
                FactRow.campaign_id == projection.campaign_id, FactRow.slug == fact.slug
            )
        )
        if fact_row is None:
            fact_row = FactRow(
                id=fact.event_id or new_id("fct"),
                campaign_id=projection.campaign_id,
                slug=fact.slug,
                text=fact.text,
                visibility=fact.visibility.value,
            )
            session.add(fact_row)
        else:
            fact_row.text = fact.text
            fact_row.visibility = fact.visibility.value

    for statement in projection.statements.values():
        statement_row = session.scalar(
            select(StatementRow).where(
                StatementRow.campaign_id == projection.campaign_id,
                StatementRow.slug == statement.slug,
            )
        )
        if statement_row is None:
            statement_row = StatementRow(
                id=statement.event_id or new_id("stm"),
                campaign_id=projection.campaign_id,
                slug=statement.slug,
                speaker_id=statement.speaker_id,
                proposition=statement.proposition,
                topic=statement.topic,
                kind=statement.kind.value,
                is_true=statement.is_true,
                audience_ids_json=list(statement.audience_ids),
            )
            session.add(statement_row)
        else:
            statement_row.proposition = statement.proposition
            statement_row.topic = statement.topic
            statement_row.kind = statement.kind.value
            statement_row.is_true = statement.is_true
            statement_row.audience_ids_json = list(statement.audience_ids)

    for knowledge in projection.knowledge.values():
        knowledge_row = session.scalar(
            select(KnowledgeRow).where(
                KnowledgeRow.campaign_id == projection.campaign_id,
                KnowledgeRow.entity_id == knowledge.entity_id,
                KnowledgeRow.statement_slug == knowledge.statement_slug,
            )
        )
        if knowledge_row is None:
            knowledge_row = KnowledgeRow(
                id=knowledge.event_id or new_id("knw"),
                campaign_id=projection.campaign_id,
                entity_id=knowledge.entity_id,
                statement_slug=knowledge.statement_slug,
                source=knowledge.source,
                event_id=knowledge.event_id,
            )
            session.add(knowledge_row)
        else:
            knowledge_row.source = knowledge.source

    for relationship in projection.relationships.values():
        relationship_row = session.scalar(
            select(RelationshipRow).where(
                RelationshipRow.campaign_id == projection.campaign_id,
                RelationshipRow.from_id == relationship.from_id,
                RelationshipRow.to_id == relationship.to_id,
                RelationshipRow.dimension == relationship.dimension.value,
            )
        )
        if relationship_row is None:
            relationship_row = RelationshipRow(
                id=relationship.updated_event_id or new_id("rel"),
                campaign_id=projection.campaign_id,
                from_id=relationship.from_id,
                to_id=relationship.to_id,
                dimension=relationship.dimension.value,
                value=relationship.value,
                event_id=relationship.updated_event_id,
            )
            session.add(relationship_row)
        else:
            relationship_row.value = relationship.value
            relationship_row.event_id = relationship.updated_event_id

    for clock in projection.clocks.values():
        clock_row = session.scalar(
            select(ClockRow).where(
                ClockRow.campaign_id == projection.campaign_id, ClockRow.slug == clock.slug
            )
        )
        if clock_row is None:
            clock_row = ClockRow(
                id=clock.created_event_id or new_id("clk"),
                campaign_id=projection.campaign_id,
                slug=clock.slug,
                name=clock.name,
                segments=clock.segments,
                filled=clock.filled,
                trigger=clock.trigger,
                owner_id=clock.owner_id,
                visibility=clock.visibility.value,
                created_event_id=clock.created_event_id,
            )
            session.add(clock_row)
        else:
            clock_row.filled = clock.filled
            clock_row.name = clock.name
            clock_row.segments = clock.segments
            clock_row.trigger = clock.trigger
            clock_row.owner_id = clock.owner_id
            clock_row.visibility = clock.visibility.value


def create_checkpoint(session: Session, campaign_id: str) -> CheckpointRow:
    projection = load_projection(session, campaign_id)
    state_hash = hash_projection(projection)
    existing = session.scalar(
        select(CheckpointRow).where(
            CheckpointRow.campaign_id == campaign_id,
            CheckpointRow.event_seq == projection.last_event_seq,
        )
    )
    if existing is not None:
        if existing.state_hash != state_hash:
            raise InvariantViolation(
                "checkpoint_conflict",
                "a different state hash is already stored for this event sequence",
            )
        return existing

    row = CheckpointRow(
        id=new_id("chk"),
        campaign_id=campaign_id,
        event_seq=projection.last_event_seq,
        state_hash=state_hash,
        snapshot_json=canonical_projection(projection),
    )
    session.add(row)
    session.flush()
    return row


def get_turn_by_client_id(
    session: Session, campaign_id: str, client_action_id: str
) -> TurnRow | None:
    return session.scalar(
        select(TurnRow).where(
            TurnRow.campaign_id == campaign_id,
            TurnRow.client_action_id == client_action_id,
        )
    )


def get_turn(session: Session, campaign_id: str, turn_id: str) -> TurnRow:
    row = session.get(TurnRow, turn_id)
    if row is None or row.campaign_id != campaign_id:
        raise NotFoundError(f"turn {turn_id!r} does not exist", turn_id=turn_id)
    return row


def next_turn_ordinal(session: Session, campaign_id: str) -> int:
    current = session.scalar(
        select(func.max(TurnRow.ordinal)).where(TurnRow.campaign_id == campaign_id)
    )
    return int(current or 0) + 1


def list_turns(
    session: Session,
    campaign_id: str,
    *,
    after_ordinal: int = 0,
    limit: int = 50,
    committed_only: bool = True,
) -> list[TurnRow]:
    statement = select(TurnRow).where(
        TurnRow.campaign_id == campaign_id,
        TurnRow.ordinal > after_ordinal,
    )
    if committed_only:
        statement = statement.where(TurnRow.status == "COMMITTED")
    return list(session.scalars(statement.order_by(TurnRow.ordinal).limit(limit)))


def list_observations(
    session: Session,
    campaign_id: str,
    *,
    after_sequence: int = 0,
    limit: int = 100,
) -> list[ObservationRow]:
    return list(
        session.scalars(
            select(ObservationRow)
            .where(
                ObservationRow.campaign_id == campaign_id,
                ObservationRow.seq > after_sequence,
            )
            .order_by(ObservationRow.seq)
            .limit(limit)
        )
    )


def observations_for_turn(session: Session, campaign_id: str, turn_id: str) -> list[ObservationRow]:
    return list(
        session.scalars(
            select(ObservationRow)
            .where(
                ObservationRow.campaign_id == campaign_id,
                ObservationRow.turn_id == turn_id,
            )
            .order_by(ObservationRow.seq)
        )
    )


def add_roll(
    session: Session,
    *,
    campaign_id: str,
    turn_id: str,
    result: dict[str, Any],
    label: str,
    formula: dict[str, Any],
    rng_algorithm: str,
    seed_ref: str,
    visibility: str = "PUBLIC",
) -> RollRow:
    row = RollRow(
        id=new_id("roll"),
        campaign_id=campaign_id,
        turn_id=turn_id,
        label=label,
        formula_json=formula,
        rng_algorithm=rng_algorithm,
        seed_ref=seed_ref,
        result_json=result,
        visibility=visibility,
    )
    session.add(row)
    session.flush()
    return row
