"""SQLAlchemy 2.x tables.

Canonical state lives in relational rows plus bounded JSON metadata. The event
ledger is append-only; projections are derived from it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class CampaignRow(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')",
            name="ck_campaigns_status",
        ),
        Index("ix_campaigns_state_version", "state_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_time: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class EntityRow(Base):
    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("campaign_id", "slug", name="uq_entities_campaign_slug"),
        Index("ix_entities_campaign_kind", "campaign_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    static_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retired_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class EntityStateRow(Base):
    __tablename__ = "entity_state"

    entity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class TurnRow(Base):
    __tablename__ = "turns"
    __table_args__ = (
        UniqueConstraint("campaign_id", "client_action_id", name="uq_turns_campaign_client_action"),
        UniqueConstraint("campaign_id", "ordinal", name="uq_turns_campaign_ordinal"),
        CheckConstraint(
            "status IN ('RECEIVED', 'PARSED', 'RESOLVED', 'NARRATED', "
            "'VALIDATED', 'COMMITTED', 'FAILED')",
            name="ck_turns_status",
        ),
        Index("ix_turns_campaign_created", "campaign_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    client_action_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    player_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    narrator_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    mechanics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    intent_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    outcome_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    rng_seed_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EventRow(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("campaign_id", "seq", name="uq_events_campaign_seq"),
        Index("ix_events_campaign_type", "campaign_id", "type"),
        Index("ix_events_turn", "turn_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("turns.id", ondelete="SET NULL"), nullable=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    inverse_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    occurred_at_world: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="PUBLIC")
    cause_event_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class RollRow(Base):
    __tablename__ = "rolls"
    __table_args__ = (
        Index("ix_rolls_campaign_turn", "campaign_id", "turn_id"),
        CheckConstraint(
            "visibility IN ('PUBLIC', 'GM_ONLY', 'ACTOR_PRIVATE', 'PLAYER_KNOWN')",
            name="ck_rolls_visibility",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("turns.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    formula_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rng_algorithm: Mapped[str] = mapped_column(String(80), nullable=False)
    seed_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="PUBLIC")


class ObservationRow(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("campaign_id", "seq", name="uq_observations_campaign_seq"),
        Index("ix_observations_campaign_turn", "campaign_id", "turn_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("turns.id", ondelete="SET NULL"), nullable=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="observation")
    subject_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="PUBLIC")
    occurred_at_world: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class CheckpointRow(Base):
    __tablename__ = "checkpoints"
    __table_args__ = (
        UniqueConstraint("campaign_id", "event_seq", name="uq_checkpoints_campaign_seq"),
        Index("ix_checkpoints_campaign_created", "campaign_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    event_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
