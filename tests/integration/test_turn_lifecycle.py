from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from atlas.domain.errors import (
    NarrationValidationError,
    TurnFailedError,
    UnparsedIntentError,
    VersionConflictError,
)
from atlas.domain.models import TurnStatus
from atlas.domain.projection import hash_projection
from atlas.game.narrator import FakeNarrator
from atlas.game.turn_service import TurnService
from atlas.persistence.orm import ObservationRow, RollRow, TurnRow
from atlas.persistence.repositories import (
    get_campaign,
    get_turn_by_client_id,
    load_events,
    load_projection,
    verify_replay,
)
from atlas.seed.broken_span import SeedResult
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker


class CrashHook:
    """Phase hook that simulates a process crash exactly once."""

    def __init__(self, phase: TurnStatus) -> None:
        self.phase = phase
        self.crashed = False
        self.phases: list[TurnStatus] = []

    def __call__(self, phase: TurnStatus, _turn_id: str) -> None:
        self.phases.append(phase)
        if phase is self.phase and not self.crashed:
            self.crashed = True
            raise RuntimeError("injected crash")


def _seed_event_count(session: Session, campaign_id: str) -> int:
    return len(load_events(session, campaign_id))


def _turn_row(session_factory: sessionmaker[Session], campaign_id: str, client_id: str) -> TurnRow:
    with session_factory() as session:
        row = get_turn_by_client_id(session, campaign_id, client_id)
        assert row is not None
        return row


def test_phase_hook_observes_the_full_lifecycle(
    session_factory: sessionmaker[Session], seed_result: SeedResult
) -> None:
    phases: list[TurnStatus] = []
    service = TurnService(session_factory, phase_hook=lambda phase, _id: phases.append(phase))

    result = service.submit_text(
        seed_result.campaign.id,
        client_action_id=str(uuid.uuid4()),
        player_text="look around",
    )

    assert result.status is TurnStatus.COMMITTED
    assert phases == [
        TurnStatus.RECEIVED,
        TurnStatus.PARSED,
        TurnStatus.RESOLVED,
        TurnStatus.NARRATED,
        TurnStatus.VALIDATED,
        TurnStatus.COMMITTED,
    ]


@pytest.mark.parametrize(
    "crash_phase",
    [
        TurnStatus.RECEIVED,
        TurnStatus.PARSED,
        TurnStatus.RESOLVED,
        TurnStatus.NARRATED,
        TurnStatus.VALIDATED,
        TurnStatus.COMMITTED,
    ],
)
def test_crash_after_each_phase_resumes_without_double_apply(
    session: Session,
    session_factory: sessionmaker[Session],
    seed_result: SeedResult,
    crash_phase: TurnStatus,
) -> None:
    campaign_id = seed_result.campaign.id
    client_id = str(uuid.uuid4())
    hook = CrashHook(crash_phase)
    service = TurnService(session_factory, phase_hook=hook)
    before_events = _seed_event_count(session, campaign_id)
    before_hash = hash_projection(load_projection(session, campaign_id))

    with pytest.raises(RuntimeError, match="injected crash"):
        service.submit_text(
            campaign_id,
            client_action_id=client_id,
            player_text="go to north quarry",
        )

    row = _turn_row(session_factory, campaign_id, client_id)
    assert row.status == crash_phase.value

    # A crash before COMMITTED must not have applied world state.
    if crash_phase is not TurnStatus.COMMITTED:
        with session_factory() as check:
            assert get_campaign(check, campaign_id).state_version == 0
            assert _seed_event_count(check, campaign_id) == before_events
            assert hash_projection(load_projection(check, campaign_id)) == before_hash

    recovered = service.submit_text(
        campaign_id,
        client_action_id=client_id,
        player_text="go to north quarry",
    )

    assert recovered.status is TurnStatus.COMMITTED
    assert recovered.turn_id == row.id
    assert recovered.campaign_version == 1

    with session_factory() as check:
        campaign = get_campaign(check, campaign_id)
        projection = load_projection(check, campaign_id)
        actor = projection.entity_by_slug("rowan")
        quarry = projection.entity_by_slug("quarry")
        assert actor is not None and quarry is not None
        assert campaign.state_version == 1
        assert campaign.current_time == 30
        assert actor.state["location_id"] == quarry.id
        assert projection.observations == [
            observation for observation in projection.observations if observation.kind == "arrival"
        ]
        assert len(projection.observations) == 1
        assert _seed_event_count(check, campaign_id) == before_events + 4
        assert verify_replay(check, campaign_id).matched

        committed_row = get_turn_by_client_id(check, campaign_id, client_id)
        assert committed_row is not None
        assert committed_row.status == TurnStatus.COMMITTED.value
        expected_attempts = 1 if crash_phase in (TurnStatus.RECEIVED, TurnStatus.COMMITTED) else 2
        assert committed_row.attempt_count == expected_attempts


def test_recovery_reuses_the_persisted_seed_and_roll(
    session_factory: sessionmaker[Session], seed_result: SeedResult
) -> None:
    campaign_id = seed_result.campaign.id
    client_id = str(uuid.uuid4())
    service = TurnService(session_factory, phase_hook=CrashHook(TurnStatus.RESOLVED))

    with pytest.raises(RuntimeError):
        service.submit_text(
            campaign_id,
            client_action_id=client_id,
            player_text="search the square",
        )

    row = _turn_row(session_factory, campaign_id, client_id)
    assert row.outcome_json is not None
    stored_roll = row.outcome_json["roll"]
    stored_seed = row.rng_seed_hex

    first = service.submit_text(
        campaign_id,
        client_action_id=client_id,
        player_text="search the square",
    )
    assert first.roll is not None
    assert first.roll.dice == stored_roll["dice"]
    assert first.roll.total == stored_roll["total"]
    assert first.roll.outcome.value == stored_roll["outcome"]

    with session_factory() as check:
        recovered_row = get_turn_by_client_id(check, campaign_id, client_id)
        assert recovered_row is not None
        assert recovered_row.rng_seed_hex == stored_seed
        roll_rows = check.scalars(select(RollRow)).all()
        assert len(roll_rows) == 1


def test_commit_failure_rolls_back_events_and_projection(
    session: Session,
    session_factory: sessionmaker[Session],
    seed_result: SeedResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id = seed_result.campaign.id
    before_events = _seed_event_count(session, campaign_id)
    before_hash = hash_projection(load_projection(session, campaign_id))

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected write failure after event insertion")

    # add_roll runs after events are inserted in the commit transaction, so a
    # failure here proves the whole commit is rolled back.
    monkeypatch.setattr("atlas.game.turn_service.add_roll", _explode)

    service = TurnService(session_factory)
    with pytest.raises(RuntimeError, match="injected write failure"):
        service.submit_text(
            campaign_id,
            client_action_id=str(uuid.uuid4()),
            player_text="search the square",
        )

    with session_factory() as check:
        assert get_campaign(check, campaign_id).state_version == 0
        assert _seed_event_count(check, campaign_id) == before_events
        assert hash_projection(load_projection(check, campaign_id)) == before_hash
        assert check.scalar(select(func.count(ObservationRow.id))) == 0
        assert check.scalar(select(func.count(RollRow.id))) == 0
        rows = check.scalars(select(TurnRow)).all()
        assert len(rows) == 1
        assert rows[0].status == TurnStatus.VALIDATED.value


def test_stale_pending_turn_is_failed_without_applying_effects(
    session_factory: sessionmaker[Session], seed_result: SeedResult
) -> None:
    campaign_id = seed_result.campaign.id
    stale_client = str(uuid.uuid4())
    crashing = TurnService(session_factory, phase_hook=CrashHook(TurnStatus.PARSED))

    with pytest.raises(RuntimeError):
        crashing.submit_text(
            campaign_id,
            client_action_id=stale_client,
            player_text="go to north quarry",
        )

    fresh = TurnService(session_factory)
    fresh.submit_text(
        campaign_id,
        client_action_id=str(uuid.uuid4()),
        player_text="look around",
    )

    with pytest.raises(VersionConflictError):
        fresh.submit_text(
            campaign_id,
            client_action_id=stale_client,
            player_text="go to north quarry",
        )

    with session_factory() as check:
        row = get_turn_by_client_id(check, campaign_id, stale_client)
        assert row is not None
        assert row.status == TurnStatus.FAILED.value
        assert row.error_code == "version_conflict"
        projection = load_projection(check, campaign_id)
        actor = projection.entity_by_slug("rowan")
        square = projection.entity_by_slug("town_square")
        assert actor is not None and square is not None
        assert actor.state["location_id"] == square.id
        assert verify_replay(check, campaign_id).matched


def test_unparsed_text_fails_durably_and_never_mutates_state(
    session: Session,
    session_factory: sessionmaker[Session],
    seed_result: SeedResult,
) -> None:
    campaign_id = seed_result.campaign.id
    client_id = str(uuid.uuid4())
    before_events = _seed_event_count(session, campaign_id)
    service = TurnService(session_factory)

    with pytest.raises(UnparsedIntentError):
        service.submit_text(
            campaign_id,
            client_action_id=client_id,
            player_text="summon a dragon",
        )

    with session_factory() as check:
        row = get_turn_by_client_id(check, campaign_id, client_id)
        assert row is not None
        assert row.status == TurnStatus.FAILED.value
        assert row.error_code == "unparsed_intent"
        assert get_campaign(check, campaign_id).state_version == 0
        assert _seed_event_count(check, campaign_id) == before_events

    with pytest.raises(TurnFailedError):
        service.submit_text(
            campaign_id,
            client_action_id=client_id,
            player_text="look around",
        )


def test_narration_secret_leak_is_rejected_before_commit(
    session: Session,
    session_factory: sessionmaker[Session],
    seed_result: SeedResult,
) -> None:
    campaign_id = seed_result.campaign.id
    before_events = _seed_event_count(session, campaign_id)
    narrator = FakeNarrator(scripted=["The M0_GM_ONLY_CARAVAN_STONE_SOURCE is nearby."])
    service = TurnService(session_factory, narrator=narrator)

    with pytest.raises(NarrationValidationError):
        service.submit_text(
            campaign_id,
            client_action_id=str(uuid.uuid4()),
            player_text="look around",
        )

    with session_factory() as check:
        assert get_campaign(check, campaign_id).state_version == 0
        assert _seed_event_count(check, campaign_id) == before_events
        row = check.scalars(select(TurnRow)).one()
        assert row.status == TurnStatus.FAILED.value
        assert row.error_code == "narrator_invalid"
        assert row.narrator_text is None


def test_same_client_concurrent_duplicate_applies_once(
    session_factory: sessionmaker[Session], seed_result: SeedResult
) -> None:
    campaign_id = seed_result.campaign.id
    client_id = str(uuid.uuid4())
    service = TurnService(session_factory)

    def _submit() -> str:
        return service.submit_text(
            campaign_id,
            client_action_id=client_id,
            player_text="wait 10 minutes",
        ).turn_id

    with ThreadPoolExecutor(max_workers=4) as pool:
        turn_ids = list(pool.map(lambda _: _submit(), range(4)))

    assert len(set(turn_ids)) == 1

    with session_factory() as check:
        rows = check.scalars(select(TurnRow).where(TurnRow.client_action_id == client_id)).all()
        assert len(rows) == 1
        assert rows[0].status == TurnStatus.COMMITTED.value
        campaign = get_campaign(check, campaign_id)
        assert campaign.state_version == 1
        assert campaign.current_time == 10
        assert verify_replay(check, campaign_id).matched


def test_concurrent_distinct_actions_commit_distinct_ordinals(
    session_factory: sessionmaker[Session], seed_result: SeedResult
) -> None:
    campaign_id = seed_result.campaign.id
    service = TurnService(session_factory)

    def _submit(_: int) -> int:
        result = service.submit_text(
            campaign_id,
            client_action_id=str(uuid.uuid4()),
            player_text="look around",
        )
        return result.ordinal

    with ThreadPoolExecutor(max_workers=4) as pool:
        ordinals = list(pool.map(_submit, range(4)))

    assert sorted(ordinals) == [1, 2, 3, 4]

    with session_factory() as check:
        assert get_campaign(check, campaign_id).state_version == 4
        turns = check.scalars(select(TurnRow).order_by(TurnRow.ordinal)).all()
        assert [turn.ordinal for turn in turns] == [1, 2, 3, 4]
        assert all(turn.status == TurnStatus.COMMITTED.value for turn in turns)
        assert verify_replay(check, campaign_id).matched


def test_hundred_turn_text_simulation_replays_exactly(
    session_factory: sessionmaker[Session], seed_result: SeedResult
) -> None:
    campaign_id = seed_result.campaign.id
    service = TurnService(session_factory)
    script = [
        "look around",
        "go to north quarry",
        "search the quarry",
        "wait 15 minutes",
        "go to market square",
        "talk to the magistrate",
        "look around",
        "wait 1 hour",
    ]
    requests: list[tuple[str, str]] = [
        (str(uuid.uuid4()), script[index % len(script)]) for index in range(100)
    ]

    results = [
        service.submit_text(
            campaign_id,
            client_action_id=client_id,
            player_text=text,
        )
        for client_id, text in requests
    ]

    assert [result.ordinal for result in results] == list(range(1, 101))
    assert all(result.status is TurnStatus.COMMITTED for result in results)

    with session_factory() as check:
        campaign = get_campaign(check, campaign_id)
        assert campaign.state_version == 100
        turns = check.scalars(select(TurnRow).order_by(TurnRow.ordinal)).all()
        assert len(turns) == 100
        observations = check.scalars(select(ObservationRow)).all()
        assert len(observations) == 100
        report = verify_replay(check, campaign_id)
        assert report.matched
        final_hash = hash_projection(load_projection(check, campaign_id))

        # Replaying every duplicate must return stored turns, not mutate state.
        for (client_id, text), result in zip(requests, results, strict=True):
            replay = service.submit_text(
                campaign_id,
                client_action_id=client_id,
                player_text=text,
            )
            assert replay.turn_id == result.turn_id
            assert replay.narration == result.narration
        assert get_campaign(check, campaign_id).state_version == 100
        assert hash_projection(load_projection(check, campaign_id)) == final_hash
        assert len(check.scalars(select(TurnRow)).all()) == 100
