"""M2 acceptance: scripted paths reach distinct persistent endings.

Every path runs through the same public turn engine, parser, and adjudicator.
The only test-only affordance is a deterministic seed provider, so the exact
same commands can be replayed and verified from the event ledger.
"""

from __future__ import annotations

import uuid

from atlas.domain.events import parse_event_payload
from atlas.domain.projection import public_state_view
from atlas.game.turn_service import TurnService
from atlas.persistence.repositories import (
    campaign_model,
    get_campaign,
    load_events,
    load_projection,
    verify_replay,
)
from atlas.seed.broken_span import SeedResult, seed_broken_span
from sqlalchemy.orm import Session, sessionmaker


class SeedSequence:
    """Return predetermined turn seeds and fail if a path consumes too many."""

    def __init__(self, seeds: list[int]) -> None:
        self._seeds = [value.to_bytes(32, "big") for value in seeds]
        self._index = 0

    def __call__(self) -> bytes:
        assert self._index < len(self._seeds), "path used more turns than seeds were supplied"
        seed = self._seeds[self._index]
        self._index += 1
        return seed


def _service(session_factory: sessionmaker[Session], seeds: list[int]) -> TurnService:
    return TurnService(session_factory, seed_provider=SeedSequence(seeds))


def _submit(service: TurnService, campaign_id: str, text: str) -> str:
    result = service.submit_text(
        campaign_id,
        client_action_id=str(uuid.uuid4()),
        player_text=text,
    )
    assert result.status.value == "COMMITTED"
    return result.turn_id


def _open_campaign(
    session_factory: sessionmaker[Session],
    session: Session,
    *,
    template_slug: str = "river_fixer",
) -> SeedResult:
    result = seed_broken_span(session, template_slug=template_slug)
    session.commit()
    return result


def _ending(session_factory: sessionmaker[Session], campaign_id: str) -> dict[str, object] | None:
    with session_factory() as session:
        return campaign_model(get_campaign(session, campaign_id)).ending


def _assert_replay(
    session_factory: sessionmaker[Session],
    campaign_id: str,
    outcome: str,
) -> None:
    with session_factory() as session:
        campaign = campaign_model(get_campaign(session, campaign_id))
        assert campaign.status.value == "completed"
        assert isinstance(campaign.ending, dict)
        assert campaign.ending["outcome"] == outcome

        projection = load_projection(session, campaign_id)
        assert projection.status.value == "completed"
        assert projection.ending is not None
        assert projection.ending.outcome == outcome

        report = verify_replay(session, campaign_id)
        assert report.matched, report
        assert report.event_seq == len(load_events(session, campaign_id))


def test_negotiation_path_reaches_shared_guardianship(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    seeded = _open_campaign(session_factory, session, template_slug="town_advocate")
    campaign_id = seeded.campaign.id
    # Town advocate: Presence 2 + Negotiation 2 = 4, difficulty 2.
    service = _service(session_factory, [2, 4])

    _submit(service, campaign_id, "negotiate with Brannoc")
    assert _ending(session_factory, campaign_id) is None

    _submit(service, campaign_id, "negotiate with Magistrate Elin")
    _assert_replay(session_factory, campaign_id, "compromise_shared_guardianship")


def test_engineering_path_repairs_the_flood_gate(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    seeded = _open_campaign(session_factory, session, template_slug="river_fixer")
    campaign_id = seeded.campaign.id
    # Seeds: talk, move, search, gather x2, move, gather x2, move, engineer.
    service = _service(session_factory, [0, 0, 9, 2013, 2014, 0, 3002, 3004, 0, 9])

    _submit(service, campaign_id, "talk to Durn")
    _submit(service, campaign_id, "go to the quarry")
    _submit(service, campaign_id, "search the quarry")
    _submit(service, campaign_id, "gather replacement stones")
    _submit(service, campaign_id, "gather replacement stones")
    _submit(service, campaign_id, "go to the workshop")
    _submit(service, campaign_id, "gather timber")
    _submit(service, campaign_id, "gather iron fittings")
    _submit(service, campaign_id, "go to the flood gate")
    _submit(service, campaign_id, "repair the flood gate")

    _assert_replay(session_factory, campaign_id, "flood_gate_repaired")


def test_confrontation_path_drives_the_giant_off(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    seeded = _open_campaign(session_factory, session, template_slug="stone_warden")
    campaign_id = seeded.campaign.id
    # Stone warden: Might 2 + Confrontation 1 = 3, difficulty 2.
    service = _service(session_factory, [1007])

    _submit(service, campaign_id, "confront Brannoc")
    _assert_replay(session_factory, campaign_id, "giant_driven_off")


def test_returning_the_stones_reaches_a_sacrifice_ending(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    seeded = _open_campaign(session_factory, session, template_slug="river_fixer")
    campaign_id = seeded.campaign.id
    # Move, gather x2 (2 + 1 stones), then three single gifts.
    service = _service(session_factory, [0, 2013, 2014, 0, 0, 0])

    _submit(service, campaign_id, "go to the flood gate")
    _submit(service, campaign_id, "gather sacred stones")
    _submit(service, campaign_id, "gather sacred stones")
    _submit(service, campaign_id, "give sacred stones to Brannoc")
    _submit(service, campaign_id, "give sacred stones to Brannoc")
    assert _ending(session_factory, campaign_id) is None
    _submit(service, campaign_id, "give sacred stones to Brannoc")

    _assert_replay(session_factory, campaign_id, "stones_returned")


def test_abandoning_the_town_is_a_distinct_ending(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    seeded = _open_campaign(session_factory, session)
    campaign_id = seeded.campaign.id
    service = _service(session_factory, [0])

    _submit(service, campaign_id, "abandon the town")
    _assert_replay(session_factory, campaign_id, "town_abandoned")


def test_storm_clock_fills_and_forces_the_flood_ending(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    seeded = _open_campaign(session_factory, session)
    campaign_id = seeded.campaign.id
    service = _service(session_factory, [0])

    _submit(service, campaign_id, "wait 12 hours")

    _assert_replay(session_factory, campaign_id, "storm_flood")
    with session_factory() as check:
        projection = load_projection(check, campaign_id)
        storm = projection.clocks["storm_arrival"]
        assert storm.filled == storm.segments


def test_each_path_leaves_a_different_persistent_ending(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    outcomes = set()
    for template, seeds, actions in [
        ("town_advocate", [2, 4], ["negotiate with Brannoc", "negotiate with Magistrate Elin"]),
        ("stone_warden", [1007], ["confront Brannoc"]),
        ("river_fixer", [0], ["abandon the town"]),
    ]:
        seeded = seed_broken_span(session, template_slug=template)
        session.commit()
        campaign_id = seeded.campaign.id
        service = _service(session_factory, seeds)
        for action in actions:
            _submit(service, campaign_id, action)
        ending = _ending(session_factory, campaign_id)
        assert ending is not None
        outcomes.add(str(ending["outcome"]))
        with session_factory() as check:
            check.expire_all()
            assert verify_replay(check, campaign_id).matched
    assert len(outcomes) == 3


def test_player_state_never_exposes_hidden_truth(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    seeded = _open_campaign(session_factory, session)
    campaign_id = seeded.campaign.id
    service = _service(session_factory, [0])
    _submit(service, campaign_id, "talk to Brannoc")

    with session_factory() as check:
        projection = load_projection(check, campaign_id)
        view = public_state_view(projection)
        rendered = repr(view)
        assert "is_true" not in rendered
        assert "caravan_guild_secret" not in rendered
        assert "M0_GM_ONLY_CARAVAN_STONE_SOURCE" not in rendered
        assert all(
            entry["kind"] != "statement" and "is_true" not in entry for entry in view["knowledge"]
        )


def test_gift_moves_inventory_between_characters(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    seeded = _open_campaign(session_factory, session)
    campaign_id = seeded.campaign.id
    service = _service(session_factory, [0, 2013, 2014, 0])

    _submit(service, campaign_id, "go to the flood gate")
    _submit(service, campaign_id, "gather sacred stones")
    _submit(service, campaign_id, "gather sacred stones")
    _submit(service, campaign_id, "give sacred stones to Brannoc")

    with session_factory() as check:
        projection = load_projection(check, campaign_id)
        rowan = projection.entity_by_slug("rowan")
        brannoc = projection.entity_by_slug("brannoc")
        assert rowan is not None and brannoc is not None
        assert rowan.state["inventory"]["sacred_stones"]["quantity"] == 2
        assert brannoc.state["inventory"]["sacred_stones"]["quantity"] == 1


def test_events_record_every_m2_truth_kind(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    seeded = _open_campaign(session_factory, session)
    campaign_id = seeded.campaign.id
    service = _service(session_factory, [0, 2013])
    _submit(service, campaign_id, "go to the flood gate")
    _submit(service, campaign_id, "gather sacred stones")

    with session_factory() as check:
        types = {event.event_type.value for event in load_events(check, campaign_id)}
        assert {
            "fact.recorded",
            "statement.recorded",
            "knowledge.recorded",
            "relationship.changed",
            "clock.created",
            "item.transferred",
        } <= types
        for event in load_events(check, campaign_id):
            parse_event_payload(event.event_type, event.payload)
