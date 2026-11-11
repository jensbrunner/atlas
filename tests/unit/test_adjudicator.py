from __future__ import annotations

import pytest
from atlas.domain.commands import (
    AdjustResourceCommand,
    AdvanceTimeCommand,
    MoveEntityCommand,
)
from atlas.domain.dice import resolve_roll
from atlas.domain.errors import InvariantViolation
from atlas.domain.outcomes import IntentKind
from atlas.domain.projection import ProjectionState
from atlas.domain.rules import ResolutionBand, RollRequest
from atlas.game.adjudicator import DeterministicAdjudicator
from atlas.game.intent_parser import DeterministicIntentParser
from atlas.persistence.repositories import load_projection
from atlas.seed.broken_span import SeedResult
from sqlalchemy.orm import Session

SEED = bytes.fromhex("00" * 32)


@pytest.fixture
def projection(session: Session, seed_result: SeedResult) -> ProjectionState:
    return load_projection(session, seed_result.campaign.id)


@pytest.fixture
def parser() -> DeterministicIntentParser:
    return DeterministicIntentParser()


@pytest.fixture
def adjudicator() -> DeterministicAdjudicator:
    return DeterministicAdjudicator()


def test_move_emits_move_and_time_commands(
    parser: DeterministicIntentParser,
    adjudicator: DeterministicAdjudicator,
    projection: ProjectionState,
) -> None:
    intent = parser.parse("go to north quarry", projection)
    result = adjudicator.adjudicate(intent, projection, seed=SEED)

    assert result.outcome.resolution == "automatic"
    assert result.outcome.roll is None
    assert result.elapsed_minutes == 30
    assert any(isinstance(command, MoveEntityCommand) for command in result.commands)
    assert any(isinstance(command, AdvanceTimeCommand) for command in result.commands)
    assert result.outcome.observations[0].kind == "arrival"


def test_search_roll_is_reproducible_and_public(
    parser: DeterministicIntentParser,
    adjudicator: DeterministicAdjudicator,
    projection: ProjectionState,
) -> None:
    intent = parser.parse("search the square", projection)
    result = adjudicator.adjudicate(intent, projection, seed=SEED)

    assert result.roll is not None
    assert result.outcome.roll is not None
    assert "seed_ref" not in result.outcome.roll.model_dump()
    request = RollRequest(
        label=result.outcome.roll.label,
        modifier=result.outcome.roll.modifier,
        difficulty=result.outcome.roll.difficulty,
    )
    assert resolve_roll(request, SEED).public_summary() == result.outcome.roll
    assert result.outcome.resolution == result.roll.outcome.value


def _seed_for_band(band: ResolutionBand) -> bytes:
    request = RollRequest(label="probe", modifier=3, difficulty=2)
    for value in range(256):
        seed = bytes([value]) * 32
        if resolve_roll(request, seed).outcome is band:
            return seed
    raise AssertionError(f"no seed found for {band}")


def test_failed_search_never_drives_supplies_negative(
    parser: DeterministicIntentParser,
    adjudicator: DeterministicAdjudicator,
    projection: ProjectionState,
) -> None:
    actor = projection.entity_by_slug("rowan")
    assert actor is not None
    actor.state["supplies"] = 0
    intent = parser.parse("search the square", projection)
    failure_seed = _seed_for_band(ResolutionBand.FAILURE)
    result = adjudicator.adjudicate(intent, projection, seed=failure_seed)

    assert result.roll is not None
    assert result.roll.outcome is ResolutionBand.FAILURE
    assert not any(isinstance(command, AdjustResourceCommand) for command in result.commands)


def test_successful_search_adds_supplies_within_bounds(
    parser: DeterministicIntentParser,
    adjudicator: DeterministicAdjudicator,
    projection: ProjectionState,
) -> None:
    actor = projection.entity_by_slug("rowan")
    assert actor is not None
    actor.state["supplies"] = 0
    intent = parser.parse("search the square", projection)
    success_seed = _seed_for_band(ResolutionBand.SUCCESS)
    result = adjudicator.adjudicate(intent, projection, seed=success_seed)

    adjustments = [
        command for command in result.commands if isinstance(command, AdjustResourceCommand)
    ]
    assert len(adjustments) == 1
    assert adjustments[0].delta == 1


def test_move_to_an_npc_is_rejected(
    parser: DeterministicIntentParser,
    adjudicator: DeterministicAdjudicator,
    projection: ProjectionState,
) -> None:
    intent = parser.parse("go to north quarry", projection)
    npc = projection.entity_by_slug("brannoc")
    assert npc is not None
    tampered = intent.model_copy(update={"target_id": npc.id})
    with pytest.raises(InvariantViolation, match="not a location"):
        adjudicator.adjudicate(tampered, projection, seed=SEED)


def test_wait_uses_requested_minutes(
    parser: DeterministicIntentParser,
    adjudicator: DeterministicAdjudicator,
    projection: ProjectionState,
) -> None:
    intent = parser.parse("wait 45 minutes", projection)
    assert intent.kind is IntentKind.WAIT
    result = adjudicator.adjudicate(intent, projection, seed=SEED)
    assert result.elapsed_minutes == 45
    time_commands = [
        command for command in result.commands if isinstance(command, AdvanceTimeCommand)
    ]
    assert time_commands[0].minutes == 45
