"""Safe narrator boundary.

The narrator receives only approved, player-visible outcome data. It returns
prose; it never returns commands or state. Output is validated before it can be
stored with a turn.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

from atlas.domain.errors import NarrationValidationError
from atlas.domain.outcomes import IntentProposal, OutcomeProposal
from atlas.domain.projection import ProjectionState

MAX_NARRATION_LENGTH = 4_000


@dataclass(frozen=True, slots=True)
class NarrationContext:
    intent: IntentProposal | None
    outcome: OutcomeProposal
    actor_name: str
    location_name: str | None
    observations: tuple[str, ...]
    public_entity_names: tuple[str, ...]


class Narrator(Protocol):
    def narrate(self, context: NarrationContext) -> str: ...


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        collected: list[str] = []
        for item in value.values():
            collected.extend(_strings(item))
        return collected
    if isinstance(value, (list, tuple, set)):
        collected = []
        for item in value:
            collected.extend(_strings(item))
        return collected
    return []


def forbidden_markers(projection: ProjectionState) -> tuple[str, ...]:
    """Collect strings that must never appear in player-facing prose.

    GM-only entities are not merely labeled: their ids, slugs, names, and static
    values are all treated as secrets.
    """
    markers: set[str] = set()
    for entity in projection.entities.values():
        if not entity.static.get("gm_only"):
            continue
        markers.add(entity.id)
        markers.add(entity.slug)
        markers.add(entity.display_name)
        markers.update(_strings(entity.static))
    return tuple(sorted(marker for marker in markers if len(marker) >= 4))


def validate_narration(text: str, *, forbidden: tuple[str, ...] = ()) -> str:
    if not text.strip():
        raise NarrationValidationError("narration must not be empty")
    if len(text) > MAX_NARRATION_LENGTH:
        raise NarrationValidationError(
            "narration is too long",
            length=len(text),
            max=MAX_NARRATION_LENGTH,
        )
    if any(ord(character) < 32 and character not in "\n\t" for character in text):
        raise NarrationValidationError("narration contains control characters")
    lowered = text.lower()
    for marker in forbidden:
        if marker.lower() in lowered:
            raise NarrationValidationError(
                "narration references GM-only material",
                marker=marker,
            )
    return text


class FakeNarrator:
    """Deterministic offline narrator with optional scripted responses."""

    def __init__(self, scripted: list[str] | None = None) -> None:
        self._scripted: deque[str] = deque(scripted or [])

    def narrate(self, context: NarrationContext) -> str:
        if self._scripted:
            return self._scripted.popleft()

        parts: list[str] = []
        if context.observations:
            parts.append(context.observations[0])
        else:
            parts.append(context.outcome.summary)
        if context.outcome.roll is not None:
            roll = context.outcome.roll
            parts.append(
                f"The attempt ends in {roll.outcome.value} "
                f"({roll.total} against difficulty {roll.difficulty})."
            )
        if context.location_name:
            parts.append(f"{context.actor_name} is at {context.location_name}.")
        return " ".join(parts)
