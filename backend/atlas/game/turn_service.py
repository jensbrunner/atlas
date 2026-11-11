"""Transactional, lifecycle-aware turn engine.

The durable lifecycle is::

    RECEIVED -> PARSED -> RESOLVED -> NARRATED -> VALIDATED -> COMMITTED
                                                             \\
                                                              -> FAILED

Only the final commit transaction changes world state. Earlier phases persist
attempt data (intent, outcome, narration) so a crashed process can resume the
same turn and seed without applying effects twice. Events, projection rows,
rolls, and the COMMITTED status are written atomically.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from atlas.domain.commands import AdvanceTimeCommand, DomainCommand
from atlas.domain.dice import generate_seed, resolve_roll
from atlas.domain.errors import (
    DomainError,
    InvalidTurnPlanError,
    TurnFailedError,
    TurnPendingError,
    VersionConflictError,
)
from atlas.domain.events import EventDraft, EventType, SceneObservedPayload
from atlas.domain.ids import new_id
from atlas.domain.invariants import apply_commands, build_turn_committed_draft
from atlas.domain.models import EntityKind, TurnStatus
from atlas.domain.outcomes import (
    IntentKind,
    IntentProposal,
    ObservationProposal,
    OutcomeProposal,
)
from atlas.domain.projection import ProjectionState
from atlas.domain.rules import RollRequest, RollResult
from atlas.game.adjudicator import Adjudication, DeterministicAdjudicator
from atlas.game.intent_parser import DeterministicIntentParser
from atlas.game.narrator import (
    FakeNarrator,
    NarrationContext,
    Narrator,
    forbidden_markers,
    validate_narration,
)
from atlas.persistence.db import session_scope
from atlas.persistence.orm import CampaignRow, RollRow, TurnRow, utcnow
from atlas.persistence.repositories import (
    add_roll,
    commit_event_batch,
    get_campaign,
    get_turn_by_client_id,
    load_projection,
    next_turn_ordinal,
    observations_for_turn,
)

_PHASE_ORDER: tuple[TurnStatus, ...] = (
    TurnStatus.RECEIVED,
    TurnStatus.PARSED,
    TurnStatus.RESOLVED,
    TurnStatus.NARRATED,
    TurnStatus.VALIDATED,
    TurnStatus.COMMITTED,
)

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


@contextmanager
def _key_lock(key: str) -> Iterator[None]:
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, threading.Lock())
    with lock:
        yield


def _phase_index(status: TurnStatus) -> int:
    try:
        return _PHASE_ORDER.index(status)
    except ValueError:
        return -1


@dataclass(frozen=True, slots=True)
class ScriptedTurnPlan:
    """A deterministic action plan supplied by offline code or a test."""

    commands: tuple[DomainCommand, ...] = field(default_factory=tuple)
    roll_request: RollRequest | None = None
    narration_template: str | None = None
    observations: tuple[ObservationProposal, ...] = field(default_factory=tuple)


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
    intent: IntentProposal | None = None
    outcome: OutcomeProposal | None = None
    observations: tuple[ObservationProposal, ...] = field(default_factory=tuple)
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class _Attempt:
    turn_id: str
    campaign_id: str
    client_action_id: str
    ordinal: int
    player_text: str
    status: TurnStatus
    snapshot_version: int
    seed_hex: str
    attempt_count: int
    intent_json: dict[str, Any] | None
    outcome_json: dict[str, Any] | None
    narrator_text: str | None
    mechanics: dict[str, Any]
    error_code: str | None
    committed_at: datetime | None


def _attempt_from_row(row: TurnRow) -> _Attempt:
    return _Attempt(
        turn_id=row.id,
        campaign_id=row.campaign_id,
        client_action_id=row.client_action_id,
        ordinal=row.ordinal,
        player_text=row.player_text,
        status=TurnStatus(row.status),
        snapshot_version=row.snapshot_version,
        seed_hex=row.rng_seed_hex,
        attempt_count=row.attempt_count,
        intent_json=dict(row.intent_json) if row.intent_json else None,
        outcome_json=dict(row.outcome_json) if row.outcome_json else None,
        narrator_text=row.narrator_text,
        mechanics=dict(row.mechanics_json),
        error_code=row.error_code,
        committed_at=row.committed_at,
    )


class TurnService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        parser: DeterministicIntentParser | None = None,
        adjudicator: DeterministicAdjudicator | None = None,
        narrator: Narrator | None = None,
        phase_hook: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._parser = parser or DeterministicIntentParser()
        self._adjudicator = adjudicator or DeterministicAdjudicator()
        self._narrator = narrator or FakeNarrator()
        self._phase_hook = phase_hook

    # ------------------------------------------------------------------ public
    def submit_text(
        self,
        campaign_id: str,
        *,
        client_action_id: str,
        player_text: str,
        expected_version: int | None = None,
    ) -> TurnResult:
        return self._submit(
            campaign_id,
            client_action_id=client_action_id,
            player_text=player_text,
            plan=None,
            expected_version=expected_version,
        )

    def submit_plan(
        self,
        campaign_id: str,
        *,
        client_action_id: str,
        player_text: str,
        plan: ScriptedTurnPlan,
        expected_version: int | None = None,
    ) -> TurnResult:
        return self._submit(
            campaign_id,
            client_action_id=client_action_id,
            player_text=player_text,
            plan=plan,
            expected_version=expected_version,
        )

    def submit(
        self,
        campaign_id: str,
        *,
        client_action_id: str,
        player_text: str,
        plan: ScriptedTurnPlan | None = None,
        expected_version: int | None = None,
    ) -> TurnResult:
        """Backward-compatible entry point for M0 callers."""
        return self._submit(
            campaign_id,
            client_action_id=client_action_id,
            player_text=player_text,
            plan=plan,
            expected_version=expected_version,
        )

    # ------------------------------------------------------------------ driver
    def _submit(
        self,
        campaign_id: str,
        *,
        client_action_id: str,
        player_text: str,
        plan: ScriptedTurnPlan | None,
        expected_version: int | None,
    ) -> TurnResult:
        self._validate_request(client_action_id, player_text)
        key = f"{campaign_id}:{client_action_id}"
        with _key_lock(key):
            try:
                return self._drive(
                    campaign_id,
                    client_action_id=client_action_id,
                    player_text=player_text,
                    plan=plan,
                    expected_version=expected_version,
                )
            except TurnFailedError:
                raise
            except TurnPendingError:
                raise
            except DomainError as exc:
                # Phase failures are durable. A version conflict raised during
                # claim happens before a turn exists and has nothing to mark.
                self._mark_failed_if_pending(campaign_id, client_action_id, exc.code)
                raise

    def _drive(
        self,
        campaign_id: str,
        *,
        client_action_id: str,
        player_text: str,
        plan: ScriptedTurnPlan | None,
        expected_version: int | None,
    ) -> TurnResult:
        attempt, current_version = self._claim(
            campaign_id,
            client_action_id=client_action_id,
            player_text=player_text,
            expected_version=expected_version,
        )

        if attempt.status is TurnStatus.COMMITTED:
            return self._result_from_attempt(attempt)
        if attempt.status is TurnStatus.FAILED:
            raise TurnFailedError(attempt.turn_id, attempt.error_code or "unknown")

        if current_version != attempt.snapshot_version:
            self._mark_failed(attempt.turn_id, "version_conflict")
            raise VersionConflictError(attempt.snapshot_version, current_version)

        if attempt.status is not TurnStatus.RECEIVED:
            self._increment_attempt(attempt.turn_id)

        projection = self._load_snapshot(campaign_id, attempt.snapshot_version)
        seed = bytes.fromhex(attempt.seed_hex)

        if _phase_index(attempt.status) < _phase_index(TurnStatus.PARSED):
            intent = self._parse(attempt, projection, plan)
            attempt = self._set_phase(
                attempt.turn_id,
                TurnStatus.PARSED,
                allowed=(TurnStatus.RECEIVED,),
                intent_json=(
                    intent.model_dump(mode="json") if intent is not None else {"source": "scripted"}
                ),
            )
            self._call_hook(TurnStatus.PARSED, attempt.turn_id)
        else:
            intent = self._intent_from_attempt(attempt)

        outcome: OutcomeProposal
        adjudication: Adjudication | None = None
        if _phase_index(attempt.status) < _phase_index(TurnStatus.RESOLVED):
            adjudication = self._resolve(attempt, projection, plan, intent, seed)
            outcome = adjudication.outcome
            attempt = self._set_phase(
                attempt.turn_id,
                TurnStatus.RESOLVED,
                allowed=(TurnStatus.RECEIVED, TurnStatus.PARSED),
                outcome_json=outcome.model_dump(mode="json"),
            )
            self._call_hook(TurnStatus.RESOLVED, attempt.turn_id)
        else:
            outcome = self._outcome_from_attempt(attempt)

        if _phase_index(attempt.status) < _phase_index(TurnStatus.NARRATED):
            narration = self._narrate(attempt, projection, plan, intent, outcome, seed)
            validate_narration(narration, forbidden=forbidden_markers(projection))
            attempt = self._set_phase(
                attempt.turn_id,
                TurnStatus.NARRATED,
                allowed=(
                    TurnStatus.RECEIVED,
                    TurnStatus.PARSED,
                    TurnStatus.RESOLVED,
                ),
                narrator_text=narration,
            )
            self._call_hook(TurnStatus.NARRATED, attempt.turn_id)
        else:
            narration = attempt.narrator_text or ""
            validate_narration(narration, forbidden=forbidden_markers(projection))

        if _phase_index(attempt.status) < _phase_index(TurnStatus.VALIDATED):
            # Re-run the commands against the current snapshot. This is the last
            # check before the atomic commit and catches stored-attempt drift.
            self._validate_outcome(outcome, projection)
            attempt = self._set_phase(
                attempt.turn_id,
                TurnStatus.VALIDATED,
                allowed=(
                    TurnStatus.RECEIVED,
                    TurnStatus.PARSED,
                    TurnStatus.RESOLVED,
                    TurnStatus.NARRATED,
                ),
            )
            self._call_hook(TurnStatus.VALIDATED, attempt.turn_id)

        try:
            result = self._commit(attempt, outcome, narration, seed)
        except VersionConflictError as exc:
            winner = self._committed_attempt(campaign_id, client_action_id)
            if winner is not None:
                return self._result_from_attempt(winner)
            self._mark_failed(attempt.turn_id, exc.code)
            raise

        self._call_hook(TurnStatus.COMMITTED, attempt.turn_id)
        return result

    # ---------------------------------------------------------------- lifecycle
    def _claim(
        self,
        campaign_id: str,
        *,
        client_action_id: str,
        player_text: str,
        expected_version: int | None,
    ) -> tuple[_Attempt, int]:
        with self._session_factory() as session:
            existing = get_turn_by_client_id(session, campaign_id, client_action_id)
            if existing is not None:
                campaign = get_campaign(session, campaign_id)
                return _attempt_from_row(existing), campaign.state_version

        try:
            with session_scope(self._session_factory) as session:
                existing = get_turn_by_client_id(session, campaign_id, client_action_id)
                if existing is not None:
                    campaign = get_campaign(session, campaign_id)
                    return _attempt_from_row(existing), campaign.state_version

                campaign = get_campaign(session, campaign_id)
                if expected_version is not None and expected_version != campaign.state_version:
                    raise VersionConflictError(expected_version, campaign.state_version)

                # Serialize ordinal allocation for concurrent distinct actions.
                session.execute(
                    update(CampaignRow)
                    .where(CampaignRow.id == campaign_id)
                    .values(updated_at=utcnow())
                )
                projection = load_projection(session, campaign_id)
                if projection.state_version != campaign.state_version:
                    raise InvalidTurnPlanError(
                        "stored campaign version and entity projection disagree",
                        campaign_version=campaign.state_version,
                        projection_version=projection.state_version,
                    )

                ordinal = next_turn_ordinal(session, campaign_id)
                seed = generate_seed()
                row = TurnRow(
                    id=new_id("trn"),
                    campaign_id=campaign_id,
                    client_action_id=client_action_id,
                    ordinal=ordinal,
                    player_text=player_text,
                    status=TurnStatus.RECEIVED.value,
                    snapshot_version=campaign.state_version,
                    narrator_text=None,
                    mechanics_json={},
                    intent_json=None,
                    outcome_json=None,
                    attempt_count=1,
                    error_code=None,
                    rng_seed_hex=seed.hex(),
                )
                session.add(row)
                session.flush()
                return _attempt_from_row(row), campaign.state_version
        except IntegrityError:
            # A concurrent request with the same client id won the insert. Use
            # its row; a distinct action with the same ordinal will simply retry.
            with self._session_factory() as session:
                existing = get_turn_by_client_id(session, campaign_id, client_action_id)
                if existing is not None:
                    campaign = get_campaign(session, campaign_id)
                    return _attempt_from_row(existing), campaign.state_version
            return self._claim(
                campaign_id,
                client_action_id=client_action_id,
                player_text=player_text,
                expected_version=expected_version,
            )

    def _load_snapshot(self, campaign_id: str, snapshot_version: int) -> ProjectionState:
        with self._session_factory() as session:
            campaign = get_campaign(session, campaign_id)
            if campaign.state_version != snapshot_version:
                raise VersionConflictError(snapshot_version, campaign.state_version)
            projection = load_projection(session, campaign_id)
            if projection.state_version != snapshot_version:
                raise InvalidTurnPlanError(
                    "projection version does not match the turn snapshot",
                    snapshot=snapshot_version,
                    projection=projection.state_version,
                )
            return projection

    def _parse(
        self,
        attempt: _Attempt,
        projection: ProjectionState,
        plan: ScriptedTurnPlan | None,
    ) -> IntentProposal | None:
        if plan is not None:
            return None
        return self._parser.parse(
            attempt.player_text,
            projection,
            actor_slug="rowan",
        )

    def _resolve(
        self,
        attempt: _Attempt,
        projection: ProjectionState,
        plan: ScriptedTurnPlan | None,
        intent: IntentProposal | None,
        seed: bytes,
    ) -> Adjudication:
        if plan is not None:
            return self._adjudicate_plan(attempt, projection, plan, seed)
        if intent is None:
            raise InvalidTurnPlanError("turn has no parsed intent")
        return self._adjudicator.adjudicate(intent, projection, seed=seed)

    def _adjudicate_plan(
        self,
        attempt: _Attempt,
        projection: ProjectionState,
        plan: ScriptedTurnPlan,
        seed: bytes,
    ) -> Adjudication:
        application = apply_commands(projection, list(plan.commands))
        elapsed = sum(
            command.minutes for command in plan.commands if isinstance(command, AdvanceTimeCommand)
        )
        roll = resolve_roll(plan.roll_request, seed) if plan.roll_request else None
        actor = projection.entity_by_slug("rowan")
        if actor is None:
            actor = next(
                (
                    entity
                    for entity in projection.entities.values()
                    if entity.kind is EntityKind.PLAYER_CHARACTER
                ),
                None,
            )
        actor_id = actor.id if actor is not None else "ent_system"
        observations = list(plan.observations)
        summary = (
            observations[0].text
            if observations
            else f"Scripted action resolved as {roll.outcome.value if roll else 'automatic'}."
        )
        outcome = OutcomeProposal(
            actor_id=actor_id,
            kind=intent_kind_for_plan(plan),
            resolution=roll.outcome.value if roll else "automatic",
            roll=roll.public_summary() if roll else None,
            commands=list(plan.commands),
            elapsed_minutes=elapsed,
            observations=observations,
            summary=summary,
        )
        # Validate once before persisting the attempt.
        _ = application
        return Adjudication(
            outcome=outcome,
            roll=roll,
            commands=tuple(plan.commands),
            elapsed_minutes=elapsed,
        )

    def _narrate(
        self,
        attempt: _Attempt,
        projection: ProjectionState,
        plan: ScriptedTurnPlan | None,
        intent: IntentProposal | None,
        outcome: OutcomeProposal,
        seed: bytes,
    ) -> str:
        if plan is not None:
            roll = resolve_roll(plan.roll_request, seed) if plan.roll_request is not None else None
            return self._render_narration(plan, roll, outcome.elapsed_minutes)

        actor = projection.entities.get(outcome.actor_id)
        location = None
        if actor is not None:
            location_id = actor.state.get("location_id")
            if isinstance(location_id, str):
                location = projection.entities.get(location_id)
        public_names = tuple(
            sorted(
                entity.display_name
                for entity in projection.entities.values()
                if not entity.static.get("gm_only")
            )
        )
        context = NarrationContext(
            intent=intent,
            outcome=outcome,
            actor_name=actor.display_name if actor is not None else "The player",
            location_name=location.display_name if location is not None else None,
            observations=tuple(item.text for item in outcome.observations),
            public_entity_names=public_names,
        )
        return self._narrator.narrate(context)

    def _validate_outcome(self, outcome: OutcomeProposal, projection: ProjectionState) -> None:
        application = apply_commands(projection, list(outcome.commands))
        if application.projection.state_version != projection.state_version:
            raise InvalidTurnPlanError("commands changed the campaign version before commit")

    # ------------------------------------------------------------------- commit
    def _commit(
        self,
        attempt: _Attempt,
        outcome: OutcomeProposal,
        narration: str,
        seed: bytes,
    ) -> TurnResult:
        with session_scope(self._session_factory) as session:
            turn = session.get(TurnRow, attempt.turn_id)
            if turn is None:
                raise InvalidTurnPlanError(
                    "turn disappeared before commit", turn_id=attempt.turn_id
                )
            if turn.status == TurnStatus.COMMITTED.value:
                return self._result_from_row(session, turn)

            campaign = get_campaign(session, attempt.campaign_id)
            if campaign.state_version != attempt.snapshot_version:
                raise VersionConflictError(attempt.snapshot_version, campaign.state_version)

            claimed = session.execute(
                update(CampaignRow)
                .where(
                    CampaignRow.id == attempt.campaign_id,
                    CampaignRow.state_version == attempt.snapshot_version,
                )
                .values(updated_at=utcnow())
            )
            if claimed.rowcount != 1:  # type: ignore[attr-defined]
                session.refresh(campaign)
                raise VersionConflictError(attempt.snapshot_version, campaign.state_version)

            projection = load_projection(session, attempt.campaign_id)
            if projection.state_version != attempt.snapshot_version:
                raise VersionConflictError(attempt.snapshot_version, projection.state_version)

            application = apply_commands(projection, list(outcome.commands))
            drafts: list[EventDraft] = list(application.events)
            for observation in outcome.observations:
                drafts.append(
                    EventDraft(
                        event_type=EventType.SCENE_OBSERVED,
                        payload=SceneObservedPayload(
                            text=observation.text,
                            kind=observation.kind,
                            subject_ids=list(observation.subject_ids),
                        ),
                        world_time=application.projection.current_time,
                        actor_id=outcome.actor_id,
                    )
                )
            drafts.append(
                build_turn_committed_draft(
                    application.projection,
                    turn_id=attempt.turn_id,
                    ordinal=turn.ordinal,
                )
            )

            envelopes, committed = commit_event_batch(
                session,
                campaign,
                drafts,
                turn_id=attempt.turn_id,
                authority="rules_engine",
                rules_version=campaign.rules_version,
            )
            if committed.state_version != attempt.snapshot_version + 1:
                raise InvalidTurnPlanError(
                    "turn commit did not increment the campaign version",
                    expected=attempt.snapshot_version + 1,
                    actual=committed.state_version,
                )

            roll: RollResult | None = None
            if outcome.roll is not None:
                request = RollRequest(
                    label=outcome.roll.label,
                    modifier=outcome.roll.modifier,
                    difficulty=outcome.roll.difficulty,
                )
                roll = resolve_roll(request, seed)
                if roll.public_summary() != outcome.roll:
                    raise InvalidTurnPlanError(
                        "stored roll does not reproduce from the committed seed"
                    )
                add_roll(
                    session,
                    campaign_id=attempt.campaign_id,
                    turn_id=attempt.turn_id,
                    result=roll.model_dump(mode="json", exclude={"seed_ref"}),
                    label=roll.label,
                    formula={
                        "notation": "2d6",
                        "modifier": roll.modifier,
                        "difficulty": roll.difficulty,
                    },
                    rng_algorithm=roll.rng_algorithm,
                    seed_ref=roll.seed_ref,
                    visibility="PUBLIC",
                )

            mechanics: dict[str, Any] = {
                "resolution": outcome.resolution,
                "roll": (
                    outcome.roll.model_dump(mode="json") if outcome.roll is not None else None
                ),
                "commands": [command.type for command in outcome.commands],
                "elapsed_world_minutes": outcome.elapsed_minutes,
                "turn_ordinal": turn.ordinal,
                "event_ids": [envelope.event_id for envelope in envelopes],
                "observations": [item.text for item in outcome.observations],
                "intent_kind": outcome.kind.value,
            }

            turn.status = TurnStatus.COMMITTED.value
            turn.narrator_text = narration
            turn.mechanics_json = mechanics
            turn.committed_at = utcnow()
            turn.error_code = None
            session.flush()

            return TurnResult(
                turn_id=turn.id,
                status=TurnStatus.COMMITTED,
                campaign_version=attempt.snapshot_version + 1,
                ordinal=turn.ordinal,
                narration=narration,
                mechanics=mechanics,
                elapsed_world_minutes=outcome.elapsed_minutes,
                roll=roll,
                intent=self._intent_from_attempt(attempt),
                outcome=outcome,
                observations=tuple(outcome.observations),
            )

    # ---------------------------------------------------------------- retrieval
    def _result_from_attempt(self, attempt: _Attempt) -> TurnResult:
        with self._session_factory() as session:
            row = session.get(TurnRow, attempt.turn_id)
            if row is None:
                raise InvalidTurnPlanError("committed turn row is missing")
            return self._result_from_row(session, row)

    def _result_from_row(self, session: Session, row: TurnRow) -> TurnResult:
        if row.status != TurnStatus.COMMITTED.value:
            raise TurnPendingError(row.id)

        outcome = OutcomeProposal.model_validate(row.outcome_json) if row.outcome_json else None
        intent = (
            IntentProposal.model_validate(row.intent_json)
            if row.intent_json and row.intent_json.get("schema_version") == 1
            else None
        )
        roll_row = session.scalar(select(RollRow).where(RollRow.turn_id == row.id))
        roll: RollResult | None = None
        if roll_row is not None:
            payload = dict(roll_row.result_json)
            payload["rng_algorithm"] = roll_row.rng_algorithm
            payload["seed_ref"] = roll_row.seed_ref
            roll = RollResult.model_validate(payload)

        observations: tuple[ObservationProposal, ...] = ()
        if outcome is not None:
            observations = tuple(outcome.observations)
        else:
            observations = tuple(
                ObservationProposal(
                    text=observation.text,
                    kind=observation.kind,  # type: ignore[arg-type]
                    subject_ids=list(observation.subject_ids_json),
                )
                for observation in observations_for_turn(session, row.campaign_id, row.id)
            )

        mechanics = dict(row.mechanics_json)
        return TurnResult(
            turn_id=row.id,
            status=TurnStatus.COMMITTED,
            campaign_version=row.snapshot_version + 1,
            ordinal=row.ordinal,
            narration=row.narrator_text or "",
            mechanics=mechanics,
            elapsed_world_minutes=int(mechanics.get("elapsed_world_minutes", 0)),
            roll=roll,
            intent=intent,
            outcome=outcome,
            observations=observations,
        )

    def _committed_attempt(self, campaign_id: str, client_action_id: str) -> _Attempt | None:
        with self._session_factory() as session:
            row = get_turn_by_client_id(session, campaign_id, client_action_id)
            if row is not None and row.status == TurnStatus.COMMITTED.value:
                return _attempt_from_row(row)
        return None

    def _intent_from_attempt(self, attempt: _Attempt) -> IntentProposal | None:
        if not attempt.intent_json or attempt.intent_json.get("schema_version") != 1:
            return None
        return IntentProposal.model_validate(attempt.intent_json)

    def _outcome_from_attempt(self, attempt: _Attempt) -> OutcomeProposal:
        if attempt.outcome_json is None:
            raise InvalidTurnPlanError(
                "turn has no stored outcome for its lifecycle phase",
                turn_id=attempt.turn_id,
                status=attempt.status.value,
            )
        return OutcomeProposal.model_validate(attempt.outcome_json)

    # --------------------------------------------------------------- phase data
    def _set_phase(
        self,
        turn_id: str,
        phase: TurnStatus,
        *,
        allowed: tuple[TurnStatus, ...],
        **values: Any,
    ) -> _Attempt:
        with session_scope(self._session_factory) as session:
            session.execute(
                update(TurnRow)
                .where(
                    TurnRow.id == turn_id,
                    TurnRow.status.in_([status.value for status in allowed]),
                )
                .values(status=phase.value, **values)
            )
            row = session.get(TurnRow, turn_id)
            if row is None:
                raise InvalidTurnPlanError("turn disappeared during lifecycle update")
            return _attempt_from_row(row)

    def _increment_attempt(self, turn_id: str) -> None:
        with session_scope(self._session_factory) as session:
            session.execute(
                update(TurnRow)
                .where(TurnRow.id == turn_id)
                .values(attempt_count=TurnRow.attempt_count + 1)
            )

    def _mark_failed_if_pending(
        self, campaign_id: str, client_action_id: str, error_code: str
    ) -> None:
        with session_scope(self._session_factory) as session:
            row = get_turn_by_client_id(session, campaign_id, client_action_id)
            if row is not None and row.status != TurnStatus.COMMITTED.value:
                row.status = TurnStatus.FAILED.value
                row.error_code = error_code[:80]

    def _mark_failed(self, turn_id: str, error_code: str) -> None:
        with session_scope(self._session_factory) as session:
            row = session.get(TurnRow, turn_id)
            if row is not None and row.status != TurnStatus.COMMITTED.value:
                row.status = TurnStatus.FAILED.value
                row.error_code = error_code[:80]

    def _call_hook(self, phase: TurnStatus, turn_id: str) -> None:
        if self._phase_hook is not None:
            self._phase_hook(phase, turn_id)

    # ------------------------------------------------------------------ helpers
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


def intent_kind_for_plan(plan: ScriptedTurnPlan) -> IntentKind:
    if plan.roll_request is not None:
        return IntentKind.SEARCH
    return IntentKind.OBSERVE


# Backward-compatible M0 name.
OfflineTurnService = TurnService
