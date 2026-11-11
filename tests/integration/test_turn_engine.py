from __future__ import annotations

import uuid

import pytest
from atlas.domain.commands import (
    AdjustResourceCommand,
    AdvanceTimeCommand,
    MoveEntityCommand,
)
from atlas.domain.dice import resolve_roll
from atlas.domain.errors import InvariantViolation, VersionConflictError
from atlas.domain.models import ResourceName
from atlas.domain.projection import hash_projection
from atlas.domain.rules import RollRequest
from atlas.game.turn_service import OfflineTurnService, ScriptedTurnPlan, TurnResult
from atlas.persistence.orm import EventRow, RollRow, TurnRow
from atlas.persistence.repositories import (
    get_campaign,
    load_events,
    load_projection,
    verify_replay,
)
from atlas.seed.broken_span import SeedResult
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker


def _plan(session: Session, seeded: SeedResult, *, invalid: bool = False) -> ScriptedTurnPlan:
    projection = load_projection(session, seeded.campaign.id)
    pc = projection.entity_by_slug("rowan")
    quarry = projection.entity_by_slug("quarry")
    assert pc is not None and quarry is not None
    return ScriptedTurnPlan(
        commands=(
            MoveEntityCommand(
                entity_id=pc.id,
                to_location_id=quarry.id,
                reason="travel to quarry",
            ),
            AdjustResourceCommand(
                entity_id=pc.id,
                resource=ResourceName.SUPPLIES,
                delta=-99 if invalid else -1,
                reason="search supplies",
            ),
            AdvanceTimeCommand(minutes=240, reason="travel and search"),
        ),
        roll_request=RollRequest(label="quarry search", modifier=3, difficulty=2),
        narration_template="Search result: {outcome} ({total} vs {difficulty}).",
    )


def _submit(
    service: OfflineTurnService,
    campaign_id: str,
    plan: ScriptedTurnPlan,
    *,
    client_action_id: str | None = None,
    expected_version: int | None = None,
) -> TurnResult:
    return service.submit(
        campaign_id,
        client_action_id=client_action_id or str(uuid.uuid4()),
        player_text="I search the quarry.",
        plan=plan,
        expected_version=expected_version,
    )


def test_one_turn_commits_events_resources_time_and_roll(
    session: Session,
    session_factory: sessionmaker[Session],
    seed_result: SeedResult,
) -> None:
    campaign_id = seed_result.campaign.id
    plan = _plan(session, seed_result)
    result = _submit(OfflineTurnService(session_factory), campaign_id, plan, expected_version=0)

    assert result.status.value == "COMMITTED"
    assert result.campaign_version == 1
    assert result.elapsed_world_minutes == 240
    assert result.mechanics["resolution"] == result.roll.outcome.value if result.roll else False

    with session_factory() as check:
        campaign = get_campaign(check, campaign_id)
        projection = load_projection(check, campaign_id)
        pc = projection.entity_by_slug("rowan")
        quarry = projection.entity_by_slug("quarry")
        assert pc is not None and quarry is not None
        assert campaign.state_version == 1
        assert campaign.current_time == 240
        assert projection.current_time == 240
        assert pc.state["supplies"] == 1
        assert pc.state["location_id"] == quarry.id
        assert projection.entity_by_slug("sacred_stones") is not None

        turns = check.scalars(select(TurnRow)).all()
        rolls = check.scalars(select(RollRow)).all()
        assert len(turns) == 1
        assert len(rolls) == 1
        assert turns[0].status == "COMMITTED"
        assert turns[0].snapshot_version == 0
        assert len(load_events(check, campaign_id)) == 21
        assert verify_replay(check, campaign_id).matched

        # The stored seed reproduces the exact committed dice.
        request = RollRequest(label="quarry search", modifier=3, difficulty=2)
        assert resolve_roll(request, bytes.fromhex(rolls[0].seed_ref)) == result.roll


def test_duplicate_client_action_returns_same_turn_without_mutation(
    session: Session,
    session_factory: sessionmaker[Session],
    seed_result: SeedResult,
) -> None:
    campaign_id = seed_result.campaign.id
    service = OfflineTurnService(session_factory)
    client_id = str(uuid.uuid4())
    plan = _plan(session, seed_result)

    first = _submit(service, campaign_id, plan, client_action_id=client_id)
    with session_factory() as check:
        events_after_first = len(load_events(check, campaign_id))

    repeated = _submit(
        service,
        campaign_id,
        _plan(session, seed_result, invalid=True),
        client_action_id=client_id,
    )

    assert repeated.turn_id == first.turn_id
    assert repeated.campaign_version == first.campaign_version == 1
    assert repeated.narration == first.narration
    with session_factory() as check:
        assert len(load_events(check, campaign_id)) == events_after_first
        assert check.scalar(select(func.count(TurnRow.id))) == 1
        assert get_campaign(check, campaign_id).state_version == 1


def test_stale_expected_version_is_rejected_without_writes(
    session: Session,
    session_factory: sessionmaker[Session],
    seed_result: SeedResult,
) -> None:
    campaign_id = seed_result.campaign.id
    service = OfflineTurnService(session_factory)
    plan = _plan(session, seed_result)
    _submit(service, campaign_id, plan, expected_version=0)

    with session_factory() as check:
        before_events = len(load_events(check, campaign_id))

    with pytest.raises(VersionConflictError):
        _submit(service, campaign_id, _plan(session, seed_result), expected_version=0)

    with session_factory() as check:
        assert len(load_events(check, campaign_id)) == before_events
        assert get_campaign(check, campaign_id).state_version == 1
        assert check.scalar(select(func.count(TurnRow.id))) == 1


def test_invalid_command_does_not_partially_apply(
    session: Session,
    session_factory: sessionmaker[Session],
    seed_result: SeedResult,
) -> None:
    campaign_id = seed_result.campaign.id
    with session_factory() as check:
        before_hash = hash_projection(load_projection(check, campaign_id))
        before_events = len(load_events(check, campaign_id))

    with pytest.raises(InvariantViolation):
        _submit(
            OfflineTurnService(session_factory),
            campaign_id,
            _plan(session, seed_result, invalid=True),
        )

    with session_factory() as check:
        assert hash_projection(load_projection(check, campaign_id)) == before_hash
        assert len(load_events(check, campaign_id)) == before_events
        assert get_campaign(check, campaign_id).state_version == 0
        rows = check.scalars(select(TurnRow)).all()
        assert len(rows) == 1
        assert rows[0].status == "FAILED"
        assert rows[0].error_code is not None


def test_turn_committed_event_is_last_and_derives_version(
    session: Session,
    session_factory: sessionmaker[Session],
    seed_result: SeedResult,
) -> None:
    campaign_id = seed_result.campaign.id
    _submit(
        OfflineTurnService(session_factory),
        campaign_id,
        _plan(session, seed_result),
    )
    with session_factory() as check:
        events = load_events(check, campaign_id)
        assert events[-1].event_type.value == "turn.committed"
        assert events[-1].payload["state_version"] == 1
        assert events[-1].turn_id is not None
        assert check.scalar(select(func.count(EventRow.id))) == 21
