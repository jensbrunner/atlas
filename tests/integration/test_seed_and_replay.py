from __future__ import annotations

import json

from atlas.domain.projection import (
    hash_projection,
    public_state_view,
)
from atlas.persistence.db import create_db_engine, create_session_factory
from atlas.persistence.migrations import upgrade_database
from atlas.persistence.orm import EntityStateRow, EventRow
from atlas.persistence.repositories import (
    create_checkpoint,
    get_campaign,
    load_events,
    load_projection,
    replay_projection,
    verify_replay,
)
from atlas.seed.broken_span import SeedResult, seed_broken_span
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

EXPECTED_SEED_ENTITIES = 19
EXPECTED_SEED_EVENTS = 33


def test_seed_fixture_state_and_replay(session: Session, seed_result: SeedResult) -> None:
    campaign = get_campaign(session, seed_result.campaign.id)
    assert campaign.state_version == 0
    assert campaign.current_time == 0

    projection = load_projection(session, campaign.id)
    assert len(projection.entities) == EXPECTED_SEED_ENTITIES
    assert projection.entity_by_slug("rowan") is not None
    assert projection.entity_by_slug("sacred_stones") is not None
    assert projection.last_event_seq == EXPECTED_SEED_EVENTS

    events = load_events(session, campaign.id)
    assert [event.sequence for event in events] == list(range(1, EXPECTED_SEED_EVENTS + 1))

    report = verify_replay(session, campaign.id)
    assert report.matched
    assert report.event_seq == EXPECTED_SEED_EVENTS
    assert report.live_hash == hash_projection(replay_projection(session, campaign.id))


def test_public_view_never_contains_gm_only_secret(
    session: Session, seed_result: SeedResult
) -> None:
    projection = load_projection(session, seed_result.campaign.id)
    rendered = json.dumps(public_state_view(projection), sort_keys=True)
    assert "M0_GM_ONLY_CARAVAN_STONE_SOURCE" not in rendered
    assert "caravan_guild_secret" not in rendered


def test_checkpoint_matches_projection_and_is_idempotent(
    session: Session, seed_result: SeedResult
) -> None:
    projection = load_projection(session, seed_result.campaign.id)
    first = create_checkpoint(session, seed_result.campaign.id)
    second = create_checkpoint(session, seed_result.campaign.id)
    session.commit()

    assert first.id == second.id
    assert first.state_hash == hash_projection(projection)
    assert first.event_seq == projection.last_event_seq


def test_replay_detects_projection_tampering(
    session: Session, session_factory: sessionmaker[Session], seed_result: SeedResult
) -> None:
    projection = load_projection(session, seed_result.campaign.id)
    pc = projection.entity_by_slug("rowan")
    assert pc is not None

    with session_factory() as writer:
        row = writer.get(EntityStateRow, pc.id)
        assert row is not None
        state = dict(row.state_json)
        state["health"] = 999
        row.state_json = state
        writer.commit()

    report = verify_replay(session, seed_result.campaign.id)
    assert not report.matched


def test_replay_detects_event_sequence_gap(session: Session, seed_result: SeedResult) -> None:
    middle = session.scalar(
        select(EventRow).where(
            EventRow.campaign_id == seed_result.campaign.id,
            EventRow.seq == 5,
        )
    )
    assert middle is not None
    session.delete(middle)
    session.commit()

    from atlas.domain.errors import InvariantViolation

    try:
        replay_projection(session, seed_result.campaign.id)
    except InvariantViolation as exc:
        assert exc.code == "invariant.event_sequence"
    else:  # pragma: no cover
        raise AssertionError("replay did not detect an event sequence gap")


def test_state_survives_engine_reopen(database_url: str) -> None:
    upgrade_database(database_url)

    first_engine = create_db_engine(database_url)
    first_factory = create_session_factory(first_engine)
    with first_factory() as seed_session:
        seeded = seed_broken_span(seed_session)
        seed_session.commit()
        campaign_id = seeded.campaign.id
        before = load_projection(seed_session, campaign_id)
        before_hash = hash_projection(before)
    first_engine.dispose()

    second_engine = create_db_engine(database_url)
    second_factory = create_session_factory(second_engine)
    with second_factory() as reopened:
        campaign = get_campaign(reopened, campaign_id)
        after = load_projection(reopened, campaign_id)
        assert campaign.state_version == 0
        assert hash_projection(after) == before_hash
        assert verify_replay(reopened, campaign_id).matched
    second_engine.dispose()
