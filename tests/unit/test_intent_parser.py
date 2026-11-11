from __future__ import annotations

import pytest
from atlas.domain.errors import UnparsedIntentError
from atlas.domain.outcomes import IntentKind
from atlas.domain.projection import ProjectionState
from atlas.game.intent_parser import DeterministicIntentParser
from atlas.persistence.repositories import load_projection
from atlas.seed.broken_span import SeedResult
from sqlalchemy.orm import Session


@pytest.fixture
def projection(session: Session, seed_result: SeedResult) -> ProjectionState:
    return load_projection(session, seed_result.campaign.id)


@pytest.fixture
def parser() -> DeterministicIntentParser:
    return DeterministicIntentParser()


def test_move_matches_a_full_location_name(
    parser: DeterministicIntentParser, projection: ProjectionState
) -> None:
    intent = parser.parse("go to North Quarry", projection)
    assert intent.kind is IntentKind.MOVE
    assert intent.target_slug == "quarry"


def test_move_tolerates_articles_and_partial_names(
    parser: DeterministicIntentParser, projection: ProjectionState
) -> None:
    intent = parser.parse("walk to the old bridge", projection)
    assert intent.kind is IntentKind.MOVE
    assert intent.target_slug == "old_bridge"


def test_observe_has_no_target(
    parser: DeterministicIntentParser, projection: ProjectionState
) -> None:
    intent = parser.parse("look around", projection)
    assert intent.kind is IntentKind.OBSERVE
    assert intent.target_id is None


def test_search_targets_the_current_location(
    parser: DeterministicIntentParser, projection: ProjectionState
) -> None:
    intent = parser.parse("search the quarry", projection)
    assert intent.kind is IntentKind.SEARCH
    assert intent.target_slug == "town_square"


def test_speech_matches_an_npc_by_title(
    parser: DeterministicIntentParser, projection: ProjectionState
) -> None:
    intent = parser.parse("talk to the magistrate", projection)
    assert intent.kind is IntentKind.SPEAK
    assert intent.target_slug == "magistrate_elin"


def test_wait_parses_hours(parser: DeterministicIntentParser, projection: ProjectionState) -> None:
    intent = parser.parse("wait 2 hours", projection)
    assert intent.kind is IntentKind.WAIT
    assert intent.requested_minutes == 120


def test_wait_defaults_to_thirty_minutes(
    parser: DeterministicIntentParser, projection: ProjectionState
) -> None:
    intent = parser.parse("rest", projection)
    assert intent.kind is IntentKind.WAIT
    assert intent.requested_minutes == 30


def test_unknown_text_is_rejected(
    parser: DeterministicIntentParser, projection: ProjectionState
) -> None:
    with pytest.raises(UnparsedIntentError, match="did not match"):
        parser.parse("I cast a spell of infinite gold", projection)


def test_gm_only_entities_are_never_targets(
    parser: DeterministicIntentParser, projection: ProjectionState
) -> None:
    with pytest.raises(UnparsedIntentError):
        parser.parse("talk to caravan guild secret", projection)
