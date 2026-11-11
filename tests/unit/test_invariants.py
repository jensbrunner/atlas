from __future__ import annotations

import pytest
from atlas.domain.commands import (
    AdjustResourceCommand,
    AdvanceTimeCommand,
    CreateEntityCommand,
    MoveEntityCommand,
)
from atlas.domain.errors import InvariantViolation
from atlas.domain.invariants import apply_commands
from atlas.domain.models import EntityKind, ResourceName
from atlas.domain.projection import ProjectedEntity, ProjectionState
from atlas.persistence.repositories import load_projection
from atlas.seed.broken_span import SeedResult
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy.orm import Session


@pytest.fixture
def projection(session: Session, seed_result: SeedResult) -> ProjectionState:
    return load_projection(session, seed_result.campaign.id)


def _pc(projection: ProjectionState) -> ProjectedEntity:
    entity = projection.entity_by_slug("rowan")
    assert entity is not None
    return entity


def test_exact_resource_arithmetic_and_no_mutation_of_input(projection: ProjectionState) -> None:
    pc = _pc(projection)
    assert pc.state["supplies"] == 2

    spent = apply_commands(
        projection,
        [
            AdjustResourceCommand(
                entity_id=pc.id,
                resource=ResourceName.SUPPLIES,
                delta=-1,
                reason="ration",
            )
        ],
    )
    assert spent.projection.entities[pc.id].state["supplies"] == 1
    assert projection.entities[pc.id].state["supplies"] == 2

    restored = apply_commands(
        spent.projection,
        [
            AdjustResourceCommand(
                entity_id=pc.id,
                resource=ResourceName.SUPPLIES,
                delta=1,
                reason="resupply",
            )
        ],
    )
    assert restored.projection.entities[pc.id].state["supplies"] == 2


def test_negative_inventory_is_rejected(projection: ProjectionState) -> None:
    pc = _pc(projection)
    with pytest.raises(InvariantViolation, match="outside"):
        apply_commands(
            projection,
            [
                AdjustResourceCommand(
                    entity_id=pc.id,
                    resource=ResourceName.SUPPLIES,
                    delta=-3,
                    reason="overspend",
                )
            ],
        )


def test_health_cannot_exceed_entity_bounds(projection: ProjectionState) -> None:
    pc = _pc(projection)
    with pytest.raises(InvariantViolation):
        apply_commands(
            projection,
            [
                AdjustResourceCommand(
                    entity_id=pc.id,
                    resource=ResourceName.HEALTH,
                    delta=4,
                    reason="overheal",
                )
            ],
        )


def test_damage_and_healing_within_bounds(projection: ProjectionState) -> None:
    pc = _pc(projection)
    damaged = apply_commands(
        projection,
        [
            AdjustResourceCommand(
                entity_id=pc.id,
                resource=ResourceName.HEALTH,
                delta=-7,
                reason="damage",
            )
        ],
    )
    assert damaged.projection.entities[pc.id].state["health"] == 0
    healed = apply_commands(
        damaged.projection,
        [
            AdjustResourceCommand(
                entity_id=pc.id,
                resource=ResourceName.HEALTH,
                delta=2,
                reason="healing",
            )
        ],
    )
    assert healed.projection.entities[pc.id].state["health"] == 2


def test_move_requires_a_real_location(projection: ProjectionState) -> None:
    pc = _pc(projection)
    brannoc = projection.entity_by_slug("brannoc")
    assert brannoc is not None
    with pytest.raises(InvariantViolation, match="not a location"):
        apply_commands(
            projection,
            [
                MoveEntityCommand(
                    entity_id=pc.id,
                    to_location_id=brannoc.id,
                    reason="invalid destination",
                )
            ],
        )


def test_locations_cannot_move(projection: ProjectionState) -> None:
    square = projection.entity_by_slug("town_square")
    gate = projection.entity_by_slug("flood_gate")
    assert square is not None and gate is not None
    with pytest.raises(InvariantViolation, match="cannot be moved"):
        apply_commands(
            projection,
            [
                MoveEntityCommand(
                    entity_id=square.id,
                    to_location_id=gate.id,
                    reason="invalid move",
                )
            ],
        )


def test_unknown_entity_is_rejected(projection: ProjectionState) -> None:
    with pytest.raises(InvariantViolation, match="does not exist"):
        apply_commands(
            projection,
            [
                AdjustResourceCommand(
                    entity_id="ent_missing",
                    resource=ResourceName.SUPPLIES,
                    delta=-1,
                    reason="test",
                )
            ],
        )


def test_actors_require_a_location(projection: ProjectionState) -> None:
    with pytest.raises(InvariantViolation, match="physical location"):
        apply_commands(
            projection,
            [
                CreateEntityCommand(
                    kind=EntityKind.NPC,
                    slug="landless_actor",
                    display_name="Landless Actor",
                    static={},
                    state={"health": 4},
                    reason="invalid seed",
                )
            ],
        )


def test_duplicate_slug_is_rejected(projection: ProjectionState) -> None:
    with pytest.raises(InvariantViolation, match="already used"):
        apply_commands(
            projection,
            [
                CreateEntityCommand(
                    kind=EntityKind.LOCATION,
                    slug="town_square",
                    display_name="Duplicate",
                    static={},
                    state={},
                    reason="duplicate",
                )
            ],
        )


def test_time_advance_sets_world_time_for_following_events(projection: ProjectionState) -> None:
    pc = _pc(projection)
    application = apply_commands(
        projection,
        [
            AdvanceTimeCommand(minutes=90, reason="travel"),
            AdjustResourceCommand(
                entity_id=pc.id,
                resource=ResourceName.SUPPLIES,
                delta=-1,
                reason="ration after travel",
            ),
        ],
    )
    assert application.projection.current_time == 90
    assert [event.world_time for event in application.events] == [90, 90]
    assert projection.current_time == 0


@given(st.lists(st.integers(min_value=-4, max_value=4), min_size=1, max_size=20))
def test_property_resource_bounds_are_never_violated(deltas: list[int]) -> None:
    projection = ProjectionState(campaign_id="cmp_property")
    projection.entities["ent_loc"] = ProjectedEntity(
        id="ent_loc",
        campaign_id="cmp_property",
        kind=EntityKind.LOCATION,
        slug="loc",
        display_name="Location",
    )
    projection.entities["ent_pc"] = ProjectedEntity(
        id="ent_pc",
        campaign_id="cmp_property",
        kind=EntityKind.PLAYER_CHARACTER,
        slug="pc",
        display_name="PC",
        static={"resource_bounds": {"supplies": {"min": 0, "max": 9}}},
        state={"location_id": "ent_loc", "supplies": 5},
    )

    current = projection
    for delta in deltas:
        if delta == 0:
            continue
        before = current.entities["ent_pc"].state["supplies"]
        try:
            current = apply_commands(
                current,
                [
                    AdjustResourceCommand(
                        entity_id="ent_pc",
                        resource=ResourceName.SUPPLIES,
                        delta=delta,
                        reason="property test",
                    )
                ],
            ).projection
        except InvariantViolation:
            assert current.entities["ent_pc"].state["supplies"] == before
            continue
        value = current.entities["ent_pc"].state["supplies"]
        assert 0 <= value <= 9
