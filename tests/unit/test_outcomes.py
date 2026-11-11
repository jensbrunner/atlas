from __future__ import annotations

import pytest
from atlas.domain.commands import AdvanceTimeCommand
from atlas.domain.outcomes import (
    IntentKind,
    IntentProposal,
    ObservationProposal,
    OutcomeProposal,
)
from atlas.domain.rules import ResolutionBand, RollSummary
from pydantic import ValidationError


def test_move_intent_requires_a_target() -> None:
    with pytest.raises(ValidationError, match="require a target_id"):
        IntentProposal(kind=IntentKind.MOVE, actor_id="ent_actor", text="go")


def test_wait_intent_requires_minutes() -> None:
    with pytest.raises(ValidationError, match="require requested_minutes"):
        IntentProposal(kind=IntentKind.WAIT, actor_id="ent_actor", text="wait")


def test_intent_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        IntentProposal.model_validate(
            {
                "kind": IntentKind.OBSERVE,
                "actor_id": "ent_actor",
                "text": "look",
                "injected": True,
            }
        )


def test_outcome_round_trips_typed_commands() -> None:
    outcome = OutcomeProposal(
        actor_id="ent_actor",
        kind=IntentKind.WAIT,
        resolution="automatic",
        commands=[AdvanceTimeCommand(minutes=15, reason="wait")],
        elapsed_minutes=15,
        observations=[ObservationProposal(text="You wait.", kind="wait")],
        summary="You wait.",
    )
    restored = OutcomeProposal.model_validate(outcome.model_dump(mode="json"))
    assert restored == outcome
    assert restored.commands[0].type == "advance_time"


def test_outcome_requires_a_roll_for_non_automatic_resolution() -> None:
    with pytest.raises(ValidationError, match="requires a roll"):
        OutcomeProposal(
            actor_id="ent_actor",
            kind=IntentKind.SEARCH,
            resolution="success",
            summary="ok",
        )


def test_outcome_resolution_must_match_the_roll() -> None:
    roll = RollSummary(
        label="search",
        dice=[6, 6],
        modifier=0,
        difficulty=0,
        total=12,
        outcome=ResolutionBand.SUCCESS,
        rng_algorithm="hmac-sha256-ctr-v1",
    )
    with pytest.raises(ValidationError, match="must match the roll band"):
        OutcomeProposal(
            actor_id="ent_actor",
            kind=IntentKind.SEARCH,
            resolution="failure",
            roll=roll,
            summary="contradiction",
        )


def test_roll_summary_has_no_seed_reference() -> None:
    assert "seed_ref" not in RollSummary.model_fields
