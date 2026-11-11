"""Deterministic adjudication from a validated intent to typed commands.

The adjudicator never writes state. It returns an :class:`OutcomeProposal` whose
commands are re-validated against a fresh projection at commit time.
"""

from __future__ import annotations

from dataclasses import dataclass

from atlas.domain.commands import (
    AdjustResourceCommand,
    AdvanceTimeCommand,
    DomainCommand,
    MoveEntityCommand,
)
from atlas.domain.dice import resolve_roll
from atlas.domain.errors import InvariantViolation
from atlas.domain.invariants import apply_commands, resource_bounds
from atlas.domain.models import EntityKind, ResourceName
from atlas.domain.outcomes import (
    IntentKind,
    IntentProposal,
    ObservationProposal,
    OutcomeProposal,
)
from atlas.domain.projection import ProjectedEntity, ProjectionState
from atlas.domain.rules import RollRequest, RollResult

MOVE_MINUTES = 30
OBSERVE_MINUTES = 5
SEARCH_MINUTES = 60
SPEAK_MINUTES = 10
SEARCH_DIFFICULTY = 2


@dataclass(frozen=True, slots=True)
class Adjudication:
    outcome: OutcomeProposal
    roll: RollResult | None
    commands: tuple[DomainCommand, ...]
    elapsed_minutes: int


def _present_names(
    projection: ProjectionState, *, location_id: object, exclude_id: str
) -> list[str]:
    names = []
    for entity in sorted(projection.entities.values(), key=lambda item: item.display_name):
        if entity.static.get("gm_only") or entity.id == exclude_id:
            continue
        if entity.kind is EntityKind.LOCATION:
            continue
        if entity.state.get("location_id") == location_id:
            names.append(entity.display_name)
    return names


def _current_location(
    projection: ProjectionState, actor: ProjectedEntity
) -> ProjectedEntity | None:
    location_id = actor.state.get("location_id")
    if not isinstance(location_id, str):
        return None
    return projection.entities.get(location_id)


class DeterministicAdjudicator:
    """Apply ATLAS Core v0.1 resolution to one validated intent."""

    def adjudicate(
        self,
        intent: IntentProposal,
        projection: ProjectionState,
        *,
        seed: bytes,
    ) -> Adjudication:
        actor = projection.require_entity(intent.actor_id)
        if actor.kind is not EntityKind.PLAYER_CHARACTER:
            raise InvariantViolation(
                "not_a_player_character",
                "only a player character may take a turn",
                entity_id=actor.id,
            )

        if intent.kind is IntentKind.MOVE:
            return self._move(intent, actor, projection)
        if intent.kind is IntentKind.OBSERVE:
            return self._observe(intent, actor, projection)
        if intent.kind is IntentKind.SEARCH:
            return self._search(intent, actor, projection, seed)
        if intent.kind is IntentKind.SPEAK:
            return self._speak(intent, actor, projection)
        if intent.kind is IntentKind.WAIT:
            return self._wait(intent, actor, projection)
        raise InvariantViolation("unknown_intent", f"unsupported intent {intent.kind!r}")

    def _move(
        self, intent: IntentProposal, actor: ProjectedEntity, projection: ProjectionState
    ) -> Adjudication:
        target = projection.require_location(intent.target_id or "")
        commands: list[DomainCommand] = [
            MoveEntityCommand(
                entity_id=actor.id,
                to_location_id=target.id,
                reason=f"player travel: {intent.text}",
            ),
            AdvanceTimeCommand(minutes=MOVE_MINUTES, reason="travel"),
        ]
        observation = ObservationProposal(
            text=f"You travel to {target.display_name}.",
            kind="arrival",
            subject_ids=[actor.id, target.id],
        )
        return self._build(
            intent,
            actor,
            projection,
            commands=commands,
            elapsed=MOVE_MINUTES,
            observations=[observation],
            resolution="automatic",
        )

    def _observe(
        self, intent: IntentProposal, actor: ProjectedEntity, projection: ProjectionState
    ) -> Adjudication:
        location = _current_location(projection, actor)
        if location is None:
            raise InvariantViolation("missing_location", "the player has no current location")
        present = _present_names(projection, location_id=location.id, exclude_id=actor.id)
        if present:
            detail = " Present: " + ", ".join(present) + "."
        else:
            detail = " No one else is here."
        observation = ObservationProposal(
            text=f"You take in {location.display_name}.{detail}",
            kind="observation",
            subject_ids=[actor.id, location.id],
        )
        return self._build(
            intent,
            actor,
            projection,
            commands=[AdvanceTimeCommand(minutes=OBSERVE_MINUTES, reason="observe")],
            elapsed=OBSERVE_MINUTES,
            observations=[observation],
            resolution="automatic",
        )

    def _search(
        self,
        intent: IntentProposal,
        actor: ProjectedEntity,
        projection: ProjectionState,
        seed: bytes,
    ) -> Adjudication:
        location = _current_location(projection, actor)
        if location is None:
            raise InvariantViolation("missing_location", "the player has no current location")

        attributes = actor.static.get("attributes", {})
        training = actor.static.get("training", {})
        modifier = int(attributes.get("insight", 0)) + int(training.get("insight", 0))
        modifier = max(-1, min(4, modifier))
        request = RollRequest(
            label=f"search {location.slug}",
            modifier=modifier,
            difficulty=SEARCH_DIFFICULTY,
        )
        roll = resolve_roll(request, seed)

        commands: list[DomainCommand] = []
        supplies = actor.state.get(ResourceName.SUPPLIES.value)
        if isinstance(supplies, int) and not isinstance(supplies, bool):
            low, high = resource_bounds(actor.static, ResourceName.SUPPLIES)
            if roll.outcome.value == "success" and supplies < high:
                commands.append(
                    AdjustResourceCommand(
                        entity_id=actor.id,
                        resource=ResourceName.SUPPLIES,
                        delta=1,
                        reason="useful material found while searching",
                    )
                )
            elif roll.outcome.value == "failure" and supplies > low:
                commands.append(
                    AdjustResourceCommand(
                        entity_id=actor.id,
                        resource=ResourceName.SUPPLIES,
                        delta=-1,
                        reason="supplies spent on a failed search",
                    )
                )
        commands.append(AdvanceTimeCommand(minutes=SEARCH_MINUTES, reason="search"))

        if roll.outcome.value == "success":
            finding = "You find a little useful material."
        elif roll.outcome.value == "mixed_success":
            finding = "You turn up something, but not without cost."
        else:
            finding = "Nothing useful turns up."
        observation = ObservationProposal(
            text=f"You search {location.display_name}. {finding}",
            kind="search",
            subject_ids=[actor.id, location.id],
        )
        return self._build(
            intent,
            actor,
            projection,
            commands=commands,
            elapsed=SEARCH_MINUTES,
            observations=[observation],
            resolution=roll.outcome.value,
            roll=roll,
        )

    def _speak(
        self, intent: IntentProposal, actor: ProjectedEntity, projection: ProjectionState
    ) -> Adjudication:
        target = projection.require_entity(intent.target_id or "")
        if target.kind is not EntityKind.NPC:
            raise InvariantViolation(
                "not_an_npc",
                "the player can only speak with an NPC",
                entity_id=target.id,
                kind=target.kind.value,
            )
        observation = ObservationProposal(
            text=f"You speak with {target.display_name}.",
            kind="speech",
            subject_ids=[actor.id, target.id],
        )
        return self._build(
            intent,
            actor,
            projection,
            commands=[AdvanceTimeCommand(minutes=SPEAK_MINUTES, reason="conversation")],
            elapsed=SPEAK_MINUTES,
            observations=[observation],
            resolution="automatic",
        )

    def _wait(
        self, intent: IntentProposal, actor: ProjectedEntity, projection: ProjectionState
    ) -> Adjudication:
        minutes = intent.requested_minutes or 30
        location = _current_location(projection, actor)
        place = f" at {location.display_name}" if location is not None else ""
        observation = ObservationProposal(
            text=f"You wait {minutes} minutes{place}.",
            kind="wait",
            subject_ids=[actor.id, *([location.id] if location is not None else [])],
        )
        return self._build(
            intent,
            actor,
            projection,
            commands=[AdvanceTimeCommand(minutes=minutes, reason="wait")],
            elapsed=minutes,
            observations=[observation],
            resolution="automatic",
        )

    def _build(
        self,
        intent: IntentProposal,
        actor: ProjectedEntity,
        projection: ProjectionState,
        *,
        commands: list[DomainCommand],
        elapsed: int,
        observations: list[ObservationProposal],
        resolution: str,
        roll: RollResult | None = None,
    ) -> Adjudication:
        # Validate every proposed command before it can be persisted. This also
        # catches impossible travel, missing resources, and time bounds.
        apply_commands(projection, commands)
        outcome = OutcomeProposal(
            actor_id=actor.id,
            kind=intent.kind,
            resolution=resolution,  # type: ignore[arg-type]
            roll=roll.public_summary() if roll is not None else None,
            commands=commands,
            elapsed_minutes=elapsed,
            observations=observations,
            summary=observations[0].text,
        )
        return Adjudication(
            outcome=outcome,
            roll=roll,
            commands=tuple(commands),
            elapsed_minutes=elapsed,
        )
