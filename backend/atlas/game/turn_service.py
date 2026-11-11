"""M0 offline turn service.

This is deliberately a *scripted* turn pipeline, not an AI intent parser. It
proves transactional commit, seeded mechanics, idempotent replay, and rollback
before any provider is integrated. M1 replaces the plan source; the commit
boundary remains the same.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from atlas.domain.commands import AdvanceTimeCommand, DomainCommand
from atlas.domain.dice import generate_seed, resolve_roll
from atlas.domain.errors import (
    InvalidTurnPlanError,
    TurnPendingError,
    VersionConflictError,
)
from atlas.domain.ids import new_id
from atlas.domain.invariants import apply_commands, build_turn_committed_draft
from atlas.domain.models import TurnStatus
from atlas.domain.rules import RollRequest, RollResult
from atlas.persistence.db import session_scope
from atlas.persistence.orm import CampaignRow, RollRow, TurnRow, utcnow
from atlas.persistence.repositories import (
    add_roll,
    commit_event_batch,
    get_campaign,
    get_turn_by_client_id,
    load_projection,
    next_turn_ordinal,
)


@dataclass(frozen=True, slots=True)
class ScriptedTurnPlan:
    """A deterministic action plan supplied by offline code or a test."""

    commands: tuple[DomainCommand, ...] = field(default_factory=tuple)
    roll_request: RollRequest | None = None
    narration_template: str | None = None


@dataclass(frozen=True, slots=True)
class TurnResult:
    turn_id: str
    status: TurnStatus
    campaign_version: int
    ordinal: int
    narration: str
    mechanics: dict[str, Any]
    elapsed_world_minutes: int
    roll: RollResult | None = None


class OfflineTurnService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def submit(
        self,
        campaign_id: str,
        *,
        client_action_id: str,
        player_text: str,
        plan: ScriptedTurnPlan,
        expected_version: int | None = None,
    ) -> TurnResult:
        self._validate_request(client_action_id, player_text)

        with self._session_factory() as session:
            existing = get_turn_by_client_id(session, campaign_id, client_action_id)
            if existing is not None:
                return self._result_from_row(session, existing)

            campaign = get_campaign(session, campaign_id)
            snapshot_version = campaign.state_version
            if expected_version is not None and expected_version != snapshot_version:
                raise VersionConflictError(expected_version, snapshot_version)
            projection = load_projection(session, campaign_id)
            if projection.state_version != snapshot_version:
                raise InvalidTurnPlanError(
                    "stored campaign version and entity projection disagree",
                    campaign_version=snapshot_version,
                    projection_version=projection.state_version,
                )

        application = apply_commands(projection, list(plan.commands))
        elapsed = sum(
            command.minutes for command in plan.commands if isinstance(command, AdvanceTimeCommand)
        )
        seed = generate_seed()
        roll = resolve_roll(plan.roll_request, seed) if plan.roll_request else None
        narration = self._render_narration(plan, roll, elapsed)
        turn_id = new_id("trn")

        with session_scope(self._session_factory) as session:
            # A second idempotency check inside the write transaction.
            existing = get_turn_by_client_id(session, campaign_id, client_action_id)
            if existing is not None:
                return self._result_from_row(session, existing)

            campaign = get_campaign(session, campaign_id)
            if campaign.state_version != snapshot_version:
                raise VersionConflictError(snapshot_version, campaign.state_version)

            # Compare-and-swap claim of the single writer slot. This update
            # acquires SQLite's write lock before any state row is touched.
            claimed = session.execute(
                update(CampaignRow)
                .where(
                    CampaignRow.id == campaign_id,
                    CampaignRow.state_version == snapshot_version,
                )
                .values(updated_at=utcnow())
            )
            if claimed.rowcount != 1:  # type: ignore[attr-defined]
                session.refresh(campaign)
                raise VersionConflictError(snapshot_version, campaign.state_version)

            ordinal = next_turn_ordinal(session, campaign_id)
            turn = TurnRow(
                id=turn_id,
                campaign_id=campaign_id,
                client_action_id=client_action_id,
                ordinal=ordinal,
                player_text=player_text,
                status=TurnStatus.RECEIVED.value,
                snapshot_version=snapshot_version,
                narrator_text=None,
                mechanics_json={},
                error_code=None,
                rng_seed_hex=seed.hex(),
            )
            session.add(turn)
            session.flush()

            drafts = [
                *application.events,
                build_turn_committed_draft(
                    application.projection,
                    turn_id=turn_id,
                    ordinal=ordinal,
                ),
            ]
            envelopes, committed = commit_event_batch(
                session,
                campaign,
                drafts,
                turn_id=turn_id,
                authority="rules_engine",
                rules_version=campaign.rules_version,
            )
            if committed.state_version != snapshot_version + 1:
                raise InvalidTurnPlanError(
                    "turn commit did not increment the campaign version",
                    expected=snapshot_version + 1,
                    actual=committed.state_version,
                )

            mechanics: dict[str, Any] = {
                "resolution": roll.outcome.value if roll else "automatic",
                "roll": (roll.model_dump(mode="json", exclude={"seed_ref"}) if roll else None),
                "commands": [command.type for command in plan.commands],
                "elapsed_world_minutes": elapsed,
                "turn_ordinal": ordinal,
                "event_ids": [envelope.event_id for envelope in envelopes],
            }

            turn.status = TurnStatus.COMMITTED.value
            turn.narrator_text = narration
            turn.mechanics_json = mechanics
            turn.committed_at = utcnow()
            if roll is not None:
                add_roll(
                    session,
                    campaign_id=campaign_id,
                    turn_id=turn_id,
                    result=roll.model_dump(mode="json", exclude={"seed_ref"}),
                    label=roll.label,
                    formula={
                        "notation": "2d6",
                        "modifier": roll.modifier,
                        "difficulty": roll.difficulty,
                    },
                    rng_algorithm=roll.rng_algorithm,
                    seed_ref=roll.seed_ref,
                    visibility=(
                        plan.roll_request.visibility.value if plan.roll_request else "PUBLIC"
                    ),
                )

            return TurnResult(
                turn_id=turn_id,
                status=TurnStatus.COMMITTED,
                campaign_version=snapshot_version + 1,
                ordinal=ordinal,
                narration=narration,
                mechanics=mechanics,
                elapsed_world_minutes=elapsed,
                roll=roll,
            )

    def _result_from_row(self, session: Session, row: TurnRow) -> TurnResult:
        if row.status != TurnStatus.COMMITTED.value:
            raise TurnPendingError(row.id)

        mechanics = dict(row.mechanics_json)
        roll_row = session.scalar(select(RollRow).where(RollRow.turn_id == row.id))
        roll: RollResult | None = None
        if roll_row is not None:
            payload = dict(roll_row.result_json)
            payload["rng_algorithm"] = roll_row.rng_algorithm
            payload["seed_ref"] = roll_row.seed_ref
            roll = RollResult.model_validate(payload)
        return TurnResult(
            turn_id=row.id,
            status=TurnStatus.COMMITTED,
            campaign_version=row.snapshot_version + 1,
            ordinal=row.ordinal,
            narration=row.narrator_text or "",
            mechanics=mechanics,
            elapsed_world_minutes=int(mechanics.get("elapsed_world_minutes", 0)),
            roll=roll,
        )

    def _render_narration(
        self, plan: ScriptedTurnPlan, roll: RollResult | None, elapsed: int
    ) -> str:
        if plan.narration_template is None:
            if roll is None:
                return "The action is applied deterministically."
            return (
                f"The action resolves as {roll.outcome.value} "
                f"({roll.total} against difficulty {roll.difficulty})."
            )
        try:
            return plan.narration_template.format(
                outcome=roll.outcome.value if roll else "automatic",
                total=roll.total if roll else "n/a",
                difficulty=roll.difficulty if roll else "n/a",
                elapsed_minutes=elapsed,
            )
        except (KeyError, IndexError, ValueError) as exc:
            raise InvalidTurnPlanError(
                f"invalid narration template: {exc}", template=plan.narration_template
            ) from exc

    @staticmethod
    def _validate_request(client_action_id: str, player_text: str) -> None:
        try:
            uuid.UUID(client_action_id)
        except ValueError as exc:
            raise InvalidTurnPlanError(
                "client_action_id must be a UUID", client_action_id=client_action_id
            ) from exc
        if not player_text.strip():
            raise InvalidTurnPlanError("player_text must not be empty")
        if len(player_text) > 8_000:
            raise InvalidTurnPlanError("player_text is too long", length=len(player_text))
