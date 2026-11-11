"""Deterministic adjudication from a validated intent to typed commands.

The adjudicator never writes state. It returns an :class:`OutcomeProposal` whose
commands are re-validated against a fresh projection at commit time.

M2 adds four attributes, trained skills, noncombat challenges, inventory
transfers, faction clocks, and divergent campaign endings. All outcomes remain
plain deterministic rules; no model is consulted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlas.domain.characters import (
    Attribute,
    Skill,
    challenge_modifier,
    clamp_difficulty,
)
from atlas.domain.commands import (
    AdjustResourceCommand,
    AdvanceClockCommand,
    AdvanceTimeCommand,
    ChangeRelationshipCommand,
    ConsumeItemCommand,
    DomainCommand,
    EndCampaignCommand,
    GiveItemCommand,
    LearnStatementCommand,
    MoveEntityCommand,
    RecordStatementCommand,
    SetEntityFlagCommand,
    TransferItemCommand,
)
from atlas.domain.dice import resolve_roll
from atlas.domain.errors import InvariantViolation
from atlas.domain.invariants import apply_commands, resource_bounds
from atlas.domain.models import (
    EntityKind,
    RelationshipDimension,
    ResourceName,
    StatementKind,
)
from atlas.domain.outcomes import (
    IntentKind,
    IntentProposal,
    ObservationProposal,
    OutcomeProposal,
)
from atlas.domain.projection import (
    ProjectedClock,
    ProjectedEntity,
    ProjectionState,
)
from atlas.domain.rules import RollRequest, RollResult

MOVE_MINUTES = 30
OBSERVE_MINUTES = 5
SEARCH_MINUTES = 60
SPEAK_MINUTES = 10
NEGOTIATE_MINUTES = 30
ENGINEER_MINUTES = 120
CONFRONT_MINUTES = 30
GATHER_MINUTES = 60
GIVE_MINUTES = 5
ABANDON_MINUTES = 60

SEARCH_DIFFICULTY = 2
NEGOTIATE_DIFFICULTY = 2
ENGINEER_DIFFICULTY = 2
CONFRONT_DIFFICULTY = 2
GATHER_DIFFICULTY = 1

STORM_INTERVAL_MINUTES = 120

_CLOCK_ENDINGS = {
    "storm_arrival": "storm_flood",
    "giant_deadline": "bridge_collapse",
    "town_unrest": "town_revolt",
}

# Chosen so the prepared engineering path can consume exactly the seed stock.
_FLOOD_GATE_STONES = 3
_FLOOD_GATE_TIMBER = 2
_FLOOD_GATE_FITTINGS = 2

_RELATIONSHIP_MIN = -5
_RELATIONSHIP_MAX = 5


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


def _inventory(entity: ProjectedEntity) -> dict[str, Any]:
    inventory = entity.state.get("inventory")
    return inventory if isinstance(inventory, dict) else {}


def _carried(entity: ProjectedEntity, slug: str) -> int:
    entry = _inventory(entity).get(slug)
    quantity = entry.get("quantity", 0) if isinstance(entry, dict) else 0
    return quantity if isinstance(quantity, int) and not isinstance(quantity, bool) else 0


def _challenge(
    actor: ProjectedEntity,
    attribute: Attribute,
    skill: Skill,
    difficulty: int,
    seed: bytes,
    *,
    label: str,
) -> RollResult:
    request = RollRequest(
        label=label,
        modifier=challenge_modifier(actor.static, attribute, skill),
        difficulty=clamp_difficulty(difficulty),
    )
    return resolve_roll(request, seed)


def _clock_delta(projection: ProjectionState, slug: str, delta: int) -> list[DomainCommand]:
    clock = projection.clocks.get(slug)
    if clock is None or delta == 0:
        return []
    room = clock.segments - clock.filled
    if room <= 0:
        return []
    return [
        AdvanceClockCommand(
            clock_slug=slug,
            delta=min(delta, room),
            reason="clock advanced by play",
        )
    ]


def _time_clock_deltas(
    projection: ProjectionState, commands: list[DomainCommand]
) -> list[DomainCommand]:
    """Advance the storm only for explicit long time steps.

    A short look, a journey, or a conversation must not silently consume the
    storm clock. Each whole two-hour block in an explicit ``AdvanceTimeCommand``
    is one visible tick; a twelve-hour wait therefore fills the opening clock.
    """
    clock = projection.clocks.get("storm_arrival")
    if clock is None:
        return []
    ticks = sum(
        command.minutes // STORM_INTERVAL_MINUTES
        for command in commands
        if isinstance(command, AdvanceTimeCommand)
    )
    return _clock_delta(projection, "storm_arrival", ticks)


def _triggered_clock_ending(projection: ProjectionState) -> EndCampaignCommand | None:
    if projection.ending is not None:
        return None
    for slug, outcome in _CLOCK_ENDINGS.items():
        clock: ProjectedClock | None = projection.clocks.get(slug)
        if clock is not None and clock.filled >= clock.segments:
            return EndCampaignCommand(
                outcome=outcome,
                summary=clock.trigger,
                reason=f"{slug} clock filled",
            )
    return None


class DeterministicAdjudicator:
    """Apply ATLAS Core v0.2 resolution to one validated intent."""

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
        if intent.kind is IntentKind.NEGOTIATE:
            return self._negotiate(intent, actor, projection, seed)
        if intent.kind is IntentKind.ENGINEER:
            return self._engineer(intent, actor, projection, seed)
        if intent.kind is IntentKind.CONFRONT:
            return self._confront(intent, actor, projection, seed)
        if intent.kind is IntentKind.GATHER:
            return self._gather(intent, actor, projection, seed)
        if intent.kind is IntentKind.GIVE:
            return self._give(intent, actor, projection)
        if intent.kind is IntentKind.ABANDON:
            return self._abandon(intent, actor, projection)
        raise InvariantViolation("unknown_intent", f"unsupported intent {intent.kind!r}")

    # ---------------------------------------------------------------- movement
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
        detail = " Present: " + ", ".join(present) + "." if present else " No one else is here."
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

    # ----------------------------------------------------------------- search
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

        roll = _challenge(
            actor,
            Attribute.INSIGHT,
            Skill.SURVIVAL,
            SEARCH_DIFFICULTY,
            seed,
            label=f"search {location.slug}",
        )

        commands: list[DomainCommand] = []
        supplies = actor.state.get(ResourceName.SUPPLIES.value)
        if isinstance(supplies, int) and not isinstance(supplies, bool):
            low, high = resource_bounds(actor.static, ResourceName.SUPPLIES)
            if roll.outcome.value in {"success", "critical_success"} and supplies < high:
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

        discovery = self._quarry_discovery(intent, actor, projection, roll)
        if discovery is not None:
            commands.append(discovery)
        commands.append(AdvanceTimeCommand(minutes=SEARCH_MINUTES, reason="search"))

        if intent.target_slug == "quarry" and (
            projection.knows(actor.id, "durn_stone_source")
            or projection.knows(actor.id, "quarry_seam_found")
        ):
            if roll.outcome.value in {"success", "critical_success", "mixed_success"}:
                finding = "You open a seam of pale stone that rings like the sacred keystones."
            else:
                finding = "You scrabble at the quarry face but cannot open a clean seam."
        elif roll.outcome.value in {"success", "critical_success"}:
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

    def _quarry_discovery(
        self,
        intent: IntentProposal,
        actor: ProjectedEntity,
        projection: ProjectionState,
        roll: RollResult,
    ) -> RecordStatementCommand | None:
        if intent.target_slug != "quarry":
            return None
        if not projection.knows(actor.id, "durn_stone_source"):
            return None
        if "quarry_seam_found" in projection.statements:
            return None
        if roll.outcome.value not in {"success", "critical_success", "mixed_success"}:
            return None
        return RecordStatementCommand(
            statement_slug="quarry_seam_found",
            speaker_id=actor.id,
            proposition=(
                "A workable seam of sacred-compatible stone is exposed in the north quarry."
            ),
            topic="stone_source",
            kind=StatementKind.DISCOVERY,
            is_true=True,
            audience_ids=[],
            reason="player discovered the quarry seam",
        )

    # ------------------------------------------------------------------ speech
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
        commands: list[DomainCommand] = []
        told: list[str] = []
        for statement in sorted(projection.statements.values(), key=lambda item: item.slug):
            if statement.speaker_id != target.id:
                continue
            if projection.knows(actor.id, statement.slug):
                continue
            commands.append(
                LearnStatementCommand(
                    entity_id=actor.id,
                    statement_slug=statement.slug,
                    source=f"conversation:{target.slug}",
                    reason=f"{target.slug} told the player",
                )
            )
            told.append(statement.proposition)
        relationship = self._relationship_change(
            projection, actor.id, target.id, RelationshipDimension.TRUST, 1
        )
        if relationship is not None:
            commands.append(relationship)
        commands.append(AdvanceTimeCommand(minutes=SPEAK_MINUTES, reason="conversation"))

        text = f"You speak with {target.display_name}."
        if told:
            text += " They tell you: " + " ".join(told)
        observation = ObservationProposal(
            text=text,
            kind="speech",
            subject_ids=[actor.id, target.id],
        )
        return self._build(
            intent,
            actor,
            projection,
            commands=commands,
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

    # -------------------------------------------------------------- negotiation
    def _negotiate(
        self,
        intent: IntentProposal,
        actor: ProjectedEntity,
        projection: ProjectionState,
        seed: bytes,
    ) -> Adjudication:
        target = projection.require_entity(intent.target_id or "")
        if target.kind is not EntityKind.NPC:
            raise InvariantViolation(
                "not_an_npc", "negotiation requires an NPC", entity_id=target.id
            )
        roll = _challenge(
            actor,
            Attribute.PRESENCE,
            Skill.NEGOTIATION,
            NEGOTIATE_DIFFICULTY,
            seed,
            label=f"negotiate {target.slug}",
        )
        commands: list[DomainCommand] = []
        observation_kind: str = "negotiation"
        if roll.outcome.value in {"success", "critical_success"}:
            for command in (
                self._relationship_change(
                    projection, actor.id, target.id, RelationshipDimension.TRUST, 2
                ),
                self._relationship_change(
                    projection, target.id, actor.id, RelationshipDimension.RESPECT, 2
                ),
            ):
                if command is not None:
                    commands.append(command)
            commands.append(
                SetEntityFlagCommand(
                    entity_id=target.id,
                    key="accepts_shared_guard",
                    value=True,
                    reason="successful negotiation",
                )
            )
            text = f"{target.display_name} listens and accepts a shared guardianship of the stones."
            ending = self._compromise_ending(projection, target)
            if ending is not None:
                commands.append(ending)
                text += " The town and the giant have a workable accord."
                observation_kind = "ending"
        elif roll.outcome.value == "mixed_success":
            relationship = self._relationship_change(
                projection, actor.id, target.id, RelationshipDimension.TRUST, 1
            )
            if relationship is not None:
                commands.append(relationship)
            text = f"{target.display_name} hears you out but demands a concrete concession first."
        else:
            relationship = self._relationship_change(
                projection, actor.id, target.id, RelationshipDimension.TRUST, -1
            )
            if relationship is not None:
                commands.append(relationship)
            commands.extend(
                _clock_delta(
                    projection,
                    "giant_deadline" if target.slug == "brannoc" else "town_unrest",
                    1,
                )
            )
            text = f"{target.display_name} rejects your terms and the situation hardens."
        commands.append(AdvanceTimeCommand(minutes=NEGOTIATE_MINUTES, reason="negotiation"))
        observation = ObservationProposal(
            text=text,
            kind=observation_kind,  # type: ignore[arg-type]
            subject_ids=[actor.id, target.id],
        )
        return self._build(
            intent,
            actor,
            projection,
            commands=commands,
            elapsed=NEGOTIATE_MINUTES,
            observations=[observation],
            resolution=roll.outcome.value,
            roll=roll,
        )

    def _compromise_ending(
        self, projection: ProjectionState, target: ProjectedEntity
    ) -> EndCampaignCommand | None:
        if target.slug not in {"brannoc", "magistrate_elin"}:
            return None
        other_slug = "brannoc" if target.slug == "magistrate_elin" else "magistrate_elin"
        other = projection.entity_by_slug(other_slug)
        other_flags = other.state.get("flags") if other is not None else None
        other_agreed = (
            isinstance(other_flags, dict) and other_flags.get("accepts_shared_guard") is True
        )
        pending_flag = self._pending_flag(projection, target, "accepts_shared_guard")
        if other_agreed and pending_flag:
            return EndCampaignCommand(
                outcome="compromise_shared_guardianship",
                summary=(
                    "Elin's council and Brannoc agree to share custody of the stones. "
                    "The flood gate is reinforced and the giant withdraws his demand."
                ),
                reason="both parties accepted shared guardianship",
            )
        return None

    @staticmethod
    def _pending_flag(projection: ProjectionState, target: ProjectedEntity, key: str) -> bool:
        flags = target.state.get("flags")
        if isinstance(flags, dict) and flags.get(key) is True:
            return True
        # The flag command is being applied in this same turn.
        return True

    # --------------------------------------------------------------- engineering
    def _engineer(
        self,
        intent: IntentProposal,
        actor: ProjectedEntity,
        projection: ProjectionState,
        seed: bytes,
    ) -> Adjudication:
        target = projection.require_location(intent.target_id or "")
        if target.slug != "flood_gate":
            roll = _challenge(
                actor,
                Attribute.INSIGHT,
                Skill.ENGINEERING,
                ENGINEER_DIFFICULTY,
                seed,
                label=f"engineer {target.slug}",
            )
            commands: list[DomainCommand] = [
                AdvanceTimeCommand(minutes=ENGINEER_MINUTES, reason="engineering"),
            ]
            if roll.outcome.value in {"success", "critical_success", "mixed_success"}:
                commands.append(
                    SetEntityFlagCommand(
                        entity_id=target.id,
                        key="repaired",
                        value=True,
                        reason="engineering success",
                    )
                )
            observation = ObservationProposal(
                text=f"You work on {target.display_name} with mixed results.",
                kind="engineering",
                subject_ids=[actor.id, target.id],
            )
            return self._build(
                intent,
                actor,
                projection,
                commands=commands,
                elapsed=ENGINEER_MINUTES,
                observations=[observation],
                resolution=roll.outcome.value,
                roll=roll,
            )

        missing: list[str] = []
        if not projection.knows(actor.id, "quarry_seam_found"):
            missing.append("a known source of sacred-compatible stone")
        if _carried(actor, "replacement_stones") < _FLOOD_GATE_STONES:
            missing.append(f"{_FLOOD_GATE_STONES} replacement stones")
        if _carried(actor, "timber_stack") < _FLOOD_GATE_TIMBER:
            missing.append(f"{_FLOOD_GATE_TIMBER} bundles of timber")
        if _carried(actor, "iron_fittings") < _FLOOD_GATE_FITTINGS:
            missing.append(f"{_FLOOD_GATE_FITTINGS} iron fittings")
        if missing:
            observation = ObservationProposal(
                text=(
                    "You cannot repair the flood gate yet; you still need "
                    + ", ".join(missing)
                    + "."
                ),
                kind="engineering",
                subject_ids=[actor.id, target.id],
            )
            return self._build(
                intent,
                actor,
                projection,
                commands=[
                    AdvanceTimeCommand(minutes=SEARCH_MINUTES, reason="survey the flood gate")
                ],
                elapsed=SEARCH_MINUTES,
                observations=[observation],
                resolution="automatic",
            )

        roll = _challenge(
            actor,
            Attribute.INSIGHT,
            Skill.ENGINEERING,
            ENGINEER_DIFFICULTY,
            seed,
            label=f"engineer {target.slug}",
        )
        commands = [
            ConsumeItemCommand(
                holder_id=actor.id,
                item_slug="replacement_stones",
                quantity=_FLOOD_GATE_STONES,
                reason="set replacement keystones",
            ),
            ConsumeItemCommand(
                holder_id=actor.id,
                item_slug="timber_stack",
                quantity=_FLOOD_GATE_TIMBER,
                reason="brace the gate",
            ),
            ConsumeItemCommand(
                holder_id=actor.id,
                item_slug="iron_fittings",
                quantity=_FLOOD_GATE_FITTINGS,
                reason="fit iron clamps",
            ),
            AdvanceTimeCommand(minutes=ENGINEER_MINUTES, reason="engineering"),
        ]
        if roll.outcome.value in {"success", "critical_success", "mixed_success"}:
            commands.append(
                SetEntityFlagCommand(
                    entity_id=target.id,
                    key="repaired",
                    value=True,
                    reason="flood gate repaired",
                )
            )
            commands.append(
                EndCampaignCommand(
                    outcome="flood_gate_repaired",
                    summary=(
                        "Rowan sets fresh-cut sacred stones into the flood gate and braces it "
                        "before the storm. The town keeps its defenses without robbing the giant's "
                        "bridge."
                    ),
                    reason="engineering path completed",
                )
            )
            text = "You fit the fresh-cut stones and brace the flood gate. It will hold."
            kind = "ending"
        else:
            commands.extend(_clock_delta(projection, "storm_arrival", 1))
            text = "The new stone does not seat cleanly; the gate remains vulnerable."
            kind = "engineering"
        observation = ObservationProposal(
            text=text,
            kind=kind,  # type: ignore[arg-type]
            subject_ids=[actor.id, target.id],
        )
        return self._build(
            intent,
            actor,
            projection,
            commands=commands,
            elapsed=ENGINEER_MINUTES,
            observations=[observation],
            resolution=roll.outcome.value,
            roll=roll,
        )

    # ------------------------------------------------------------- confrontation
    def _confront(
        self,
        intent: IntentProposal,
        actor: ProjectedEntity,
        projection: ProjectionState,
        seed: bytes,
    ) -> Adjudication:
        target = projection.require_entity(intent.target_id or "")
        if target.kind is not EntityKind.NPC:
            raise InvariantViolation(
                "not_an_npc", "confrontation requires an NPC", entity_id=target.id
            )
        roll = _challenge(
            actor,
            Attribute.MIGHT,
            Skill.CONFRONTATION,
            CONFRONT_DIFFICULTY,
            seed,
            label=f"confront {target.slug}",
        )
        commands: list[DomainCommand] = []
        if roll.outcome.value in {"success", "critical_success"}:
            commands.append(
                SetEntityFlagCommand(
                    entity_id=target.id,
                    key="driven_off",
                    value=True,
                    reason="confrontation won",
                )
            )
            commands.append(
                EndCampaignCommand(
                    outcome=("giant_driven_off" if target.slug == "brannoc" else "threat_resolved"),
                    summary=(
                        f"Rowan faces down {target.display_name}. The immediate threat breaks, "
                        "but the town must live with the consequences of force."
                    ),
                    reason="confrontation path completed",
                )
            )
            text = f"You stand your ground and {target.display_name} backs down."
            kind = "ending"
            stress = 1
        elif roll.outcome.value == "mixed_success":
            commands.extend(_clock_delta(projection, "giant_deadline", 1))
            text = f"You wound {target.display_name}, but the standoff is not finished."
            kind = "confrontation"
            stress = 1
        else:
            commands.extend(_clock_delta(projection, "giant_deadline", 1))
            commands.extend(_clock_delta(projection, "town_unrest", 1))
            text = f"{target.display_name} beats you back; the town panics."
            kind = "confrontation"
            stress = 2
        stress_command = self._adjust_stress(actor, stress)
        if stress_command is not None:
            commands.append(stress_command)
        commands.append(AdvanceTimeCommand(minutes=CONFRONT_MINUTES, reason="confrontation"))
        observation = ObservationProposal(
            text=text,
            kind=kind,  # type: ignore[arg-type]
            subject_ids=[actor.id, target.id],
        )
        return self._build(
            intent,
            actor,
            projection,
            commands=commands,
            elapsed=CONFRONT_MINUTES,
            observations=[observation],
            resolution=roll.outcome.value,
            roll=roll,
        )

    # ------------------------------------------------------------------ gather
    def _gather(
        self,
        intent: IntentProposal,
        actor: ProjectedEntity,
        projection: ProjectionState,
        seed: bytes,
    ) -> Adjudication:
        item = projection.require_entity(intent.target_id or "")
        if item.kind is not EntityKind.ITEM:
            raise InvariantViolation("not_an_item", "gathering requires an item", entity_id=item.id)
        location_id = actor.state.get("location_id")
        if item.state.get("location_id") != location_id:
            observation = ObservationProposal(
                text=f"You must be where {item.display_name} is before you can gather it.",
                kind="observation",
                subject_ids=[actor.id, item.id],
            )
            return self._build(
                intent,
                actor,
                projection,
                commands=[AdvanceTimeCommand(minutes=SEARCH_MINUTES, reason="search for items")],
                elapsed=SEARCH_MINUTES,
                observations=[observation],
                resolution="automatic",
            )
        if item.slug == "replacement_stones" and not projection.knows(
            actor.id, "quarry_seam_found"
        ):
            observation = ObservationProposal(
                text=(
                    "You do not know which stones in the quarry will answer the old wards. "
                    "Find a reliable lead first."
                ),
                kind="observation",
                subject_ids=[actor.id, item.id],
            )
            return self._build(
                intent,
                actor,
                projection,
                commands=[AdvanceTimeCommand(minutes=SEARCH_MINUTES, reason="gather stone")],
                elapsed=SEARCH_MINUTES,
                observations=[observation],
                resolution="automatic",
            )

        difficulty = SEARCH_DIFFICULTY if item.slug == "replacement_stones" else GATHER_DIFFICULTY
        roll = _challenge(
            actor,
            Attribute.INSIGHT,
            Skill.SURVIVAL,
            difficulty,
            seed,
            label=f"gather {item.slug}",
        )
        available = item.state.get("quantity")
        available_count = (
            available if isinstance(available, int) and not isinstance(available, bool) else 0
        )
        wanted = intent.quantity
        if roll.outcome.value in {"success", "critical_success"}:
            amount = min(max(wanted, 2), available_count)
        elif roll.outcome.value == "mixed_success":
            amount = min(wanted, available_count)
        else:
            amount = 0
        commands: list[DomainCommand] = []
        if amount > 0:
            commands.append(
                TransferItemCommand(
                    item_id=item.id,
                    to_entity_id=actor.id,
                    quantity=amount,
                    reason="gathered by the player",
                )
            )
        commands.append(AdvanceTimeCommand(minutes=GATHER_MINUTES, reason="gathering"))
        if amount > 0:
            text = f"You gather {amount} x {item.display_name}."
        else:
            text = f"You fail to gather any {item.display_name}."
        observation = ObservationProposal(
            text=text,
            kind="search",
            subject_ids=[actor.id, item.id],
        )
        return self._build(
            intent,
            actor,
            projection,
            commands=commands,
            elapsed=GATHER_MINUTES,
            observations=[observation],
            resolution=roll.outcome.value,
            roll=roll,
        )

    # -------------------------------------------------------------------- give
    def _give(
        self, intent: IntentProposal, actor: ProjectedEntity, projection: ProjectionState
    ) -> Adjudication:
        target = projection.require_entity(intent.target_id or "")
        if target.kind is not EntityKind.NPC:
            raise InvariantViolation("not_an_npc", "gifts require an NPC", entity_id=target.id)
        slug = intent.item_slug or ""
        if slug not in _inventory(actor):
            raise InvariantViolation(
                "insufficient_inventory",
                "the player does not carry that item",
                item_slug=slug,
            )
        carried = _carried(actor, slug)
        quantity = min(intent.quantity, carried)
        commands: list[DomainCommand] = [
            GiveItemCommand(
                holder_id=actor.id,
                recipient_id=target.id,
                item_slug=slug,
                quantity=quantity,
                reason="player gift",
            ),
            AdvanceTimeCommand(minutes=GIVE_MINUTES, reason="gift"),
        ]
        text = f"You give {quantity} x {slug.replace('_', ' ')} to {target.display_name}."
        kind = "speech"
        if target.slug == "brannoc" and slug == "sacred_stones":
            held = _carried(target, "sacred_stones") + quantity
            if held >= 3:
                commands.append(
                    EndCampaignCommand(
                        outcome="stones_returned",
                        summary=(
                            "Brannoc takes the three sacred stones back to his bridge. "
                            "The giant is appeased, but the flood gate loses its keystones and "
                            "the lower town is exposed when the storm arrives."
                        ),
                        reason="all sacred stones returned",
                    )
                )
                text += " The giant has all three stones; the flood defense is lost."
                kind = "ending"
        observation = ObservationProposal(
            text=text,
            kind=kind,  # type: ignore[arg-type]
            subject_ids=[actor.id, target.id],
        )
        return self._build(
            intent,
            actor,
            projection,
            commands=commands,
            elapsed=GIVE_MINUTES,
            observations=[observation],
            resolution="automatic",
        )

    def _abandon(
        self, intent: IntentProposal, actor: ProjectedEntity, projection: ProjectionState
    ) -> Adjudication:
        commands: list[DomainCommand] = [
            AdvanceTimeCommand(minutes=ABANDON_MINUTES, reason="leaving town"),
            EndCampaignCommand(
                outcome="town_abandoned",
                summary=(
                    "Rowan leaves Broken Span before the storm. The town, the council, and "
                    "Brannoc must settle their quarrel without a fixer."
                ),
                reason="player abandoned the town",
            ),
        ]
        observation = ObservationProposal(
            text="You gather your tools and walk away from Broken Span.",
            kind="ending",
            subject_ids=[actor.id],
        )
        return self._build(
            intent,
            actor,
            projection,
            commands=commands,
            elapsed=ABANDON_MINUTES,
            observations=[observation],
            resolution="automatic",
        )

    # ------------------------------------------------------------------ helpers
    def _relationship_change(
        self,
        projection: ProjectionState,
        from_id: str,
        to_id: str,
        dimension: RelationshipDimension,
        delta: int,
    ) -> ChangeRelationshipCommand | None:
        current = projection.relationship_value(from_id, to_id, dimension)
        if not _RELATIONSHIP_MIN <= current + delta <= _RELATIONSHIP_MAX:
            return None
        return ChangeRelationshipCommand(
            from_id=from_id,
            to_id=to_id,
            dimension=dimension,
            delta=delta,
            reason="social consequence",
        )

    def _adjust_stress(self, actor: ProjectedEntity, delta: int) -> AdjustResourceCommand | None:
        current = actor.state.get(ResourceName.STRESS.value)
        if not isinstance(current, int) or isinstance(current, bool):
            return None
        low, high = resource_bounds(actor.static, ResourceName.STRESS)
        if not low <= current + delta <= high:
            return None
        return AdjustResourceCommand(
            entity_id=actor.id,
            resource=ResourceName.STRESS,
            delta=delta,
            reason="strain of the encounter",
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
        commands = list(commands)
        # Time-driven clocks are explicit commands, never hidden side effects.
        if not any(isinstance(command, EndCampaignCommand) for command in commands):
            commands.extend(_time_clock_deltas(projection, commands))

        # Validate every proposed command before it can be persisted.
        application = apply_commands(projection, commands)

        if not any(isinstance(command, EndCampaignCommand) for command in commands):
            ending = _triggered_clock_ending(application.projection)
            if ending is not None:
                commands.append(ending)
                observations.append(
                    ObservationProposal(
                        text=ending.summary,
                        kind="ending",
                        subject_ids=[actor.id],
                    )
                )
                application = apply_commands(projection, commands)

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
