"""Deterministic, network-free intent parsing.

This is intentionally a small grammar, not a language model. It covers the M1
verbs plus the M2 social, engineering, gathering, gift, and abandonment actions.
M3 may replace this parser with a constrained model, but the output contract and
validation remain identical.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from atlas.domain.errors import UnparsedIntentError
from atlas.domain.models import EntityKind
from atlas.domain.outcomes import IntentKind, IntentProposal
from atlas.domain.projection import ProjectedEntity, ProjectionState

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_ARTICLES = {"a", "an", "the"}
_DEFAULT_WAIT_MINUTES = 30
_MAX_WAIT_MINUTES = 10_080


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(value.lower()) if token not in _ARTICLES}


def _actor(projection: ProjectionState, actor_slug: str) -> ProjectedEntity:
    actor = projection.entity_by_slug(actor_slug)
    if actor is None:
        for entity in projection.entities.values():
            if entity.kind is EntityKind.PLAYER_CHARACTER:
                actor = entity
                break
    if actor is None or actor.kind is not EntityKind.PLAYER_CHARACTER:
        raise UnparsedIntentError("this campaign has no player character")
    return actor


def _match_entity(
    projection: ProjectionState,
    text: str,
    *,
    kinds: Iterable[EntityKind],
    exclude_id: str,
) -> ProjectedEntity:
    text_tokens = _tokens(text)
    allowed = set(kinds)
    scored: list[tuple[int, ProjectedEntity]] = []
    for entity in projection.entities.values():
        if entity.id == exclude_id or entity.kind not in allowed:
            continue
        if entity.static.get("gm_only"):
            continue
        candidate_tokens = _tokens(entity.slug) | _tokens(entity.display_name)
        if not candidate_tokens:
            continue
        overlap = candidate_tokens & text_tokens
        if not overlap:
            continue
        score = len(candidate_tokens) * 2 if candidate_tokens <= text_tokens else len(overlap)
        scored.append((score, entity))

    if not scored:
        kind_names = ", ".join(sorted(kind.value for kind in allowed))
        raise UnparsedIntentError(
            "no matching entity was found in the action",
            expected_kinds=kind_names,
        )

    scored.sort(key=lambda item: (-item[0], item[1].slug))
    best_score = scored[0][0]
    best = [entity for score, entity in scored if score == best_score]
    if len(best) > 1:
        names = sorted(entity.slug for entity in best)
        raise UnparsedIntentError(
            "the action matches more than one entity",
            candidates=names,
        )
    return best[0]


def _wait_minutes(text: str) -> int:
    match = re.search(r"(\d+)\s*(minute|minutes|min|mins|hour|hours|hr|hrs)", text.lower())
    if match is None:
        return _DEFAULT_WAIT_MINUTES
    value = int(match.group(1))
    if match.group(2).startswith(("hour", "hr")):
        value *= 60
    if not 1 <= value <= _MAX_WAIT_MINUTES:
        raise UnparsedIntentError(
            "wait duration is outside the supported range",
            minutes=value,
            min=1,
            max=_MAX_WAIT_MINUTES,
        )
    return value


class DeterministicIntentParser:
    """Parse explicit travel, observation, search, speech, social, and craft actions."""

    def parse(
        self,
        text: str,
        projection: ProjectionState,
        *,
        actor_slug: str = "rowan",
    ) -> IntentProposal:
        cleaned = " ".join(text.split())
        if not cleaned:
            raise UnparsedIntentError("player text must not be empty")
        normalized = cleaned.lower()
        actor = _actor(projection, actor_slug)

        if re.match(r"^(wait|rest)\b", normalized):
            return IntentProposal(
                kind=IntentKind.WAIT,
                actor_id=actor.id,
                requested_minutes=_wait_minutes(normalized),
                text=cleaned,
            )

        if re.match(r"^(go|move|travel|walk|head|return)\b", normalized):
            target = _match_entity(
                projection,
                normalized,
                kinds={EntityKind.LOCATION},
                exclude_id=actor.id,
            )
            return IntentProposal(
                kind=IntentKind.MOVE,
                actor_id=actor.id,
                target_id=target.id,
                target_slug=target.slug,
                text=cleaned,
            )

        if re.match(r"^(talk|speak|chat|ask)\b", normalized):
            target = _match_entity(
                projection,
                normalized,
                kinds={EntityKind.NPC},
                exclude_id=actor.id,
            )
            return IntentProposal(
                kind=IntentKind.SPEAK,
                actor_id=actor.id,
                target_id=target.id,
                target_slug=target.slug,
                text=cleaned,
            )

        if re.match(r"^(negotiate|parley|bargain|persuade)\b", normalized):
            target = _match_entity(
                projection,
                normalized,
                kinds={EntityKind.NPC},
                exclude_id=actor.id,
            )
            return IntentProposal(
                kind=IntentKind.NEGOTIATE,
                actor_id=actor.id,
                target_id=target.id,
                target_slug=target.slug,
                text=cleaned,
            )

        if re.match(r"^(confront|challenge|threaten|attack|fight)\b", normalized):
            target = _match_entity(
                projection,
                normalized,
                kinds={EntityKind.NPC},
                exclude_id=actor.id,
            )
            return IntentProposal(
                kind=IntentKind.CONFRONT,
                actor_id=actor.id,
                target_id=target.id,
                target_slug=target.slug,
                text=cleaned,
            )

        if re.match(r"^(engineer|repair|fix|rebuild|brace)\b", normalized):
            target = _match_entity(
                projection,
                normalized,
                kinds={EntityKind.LOCATION},
                exclude_id=actor.id,
            )
            return IntentProposal(
                kind=IntentKind.ENGINEER,
                actor_id=actor.id,
                target_id=target.id,
                target_slug=target.slug,
                text=cleaned,
            )

        if re.match(r"^(gather|collect|take|fetch)\b", normalized) or re.match(
            r"^pick up\b", normalized
        ):
            target = _match_entity(
                projection,
                normalized,
                kinds={EntityKind.ITEM},
                exclude_id=actor.id,
            )
            return IntentProposal(
                kind=IntentKind.GATHER,
                actor_id=actor.id,
                target_id=target.id,
                target_slug=target.slug,
                text=cleaned,
            )

        if re.match(r"^give\b", normalized):
            item = _match_entity(
                projection,
                normalized,
                kinds={EntityKind.ITEM},
                exclude_id=actor.id,
            )
            target = _match_entity(
                projection,
                normalized,
                kinds={EntityKind.NPC},
                exclude_id=actor.id,
            )
            return IntentProposal(
                kind=IntentKind.GIVE,
                actor_id=actor.id,
                target_id=target.id,
                target_slug=target.slug,
                item_slug=item.slug,
                quantity=1,
                text=cleaned,
            )

        if re.match(r"^(abandon|flee|forfeit)\b", normalized):
            return IntentProposal(
                kind=IntentKind.ABANDON,
                actor_id=actor.id,
                text=cleaned,
            )

        if re.match(r"^(search|scavenge|investigate)\b", normalized) or re.match(
            r"^look for\b", normalized
        ):
            location_id = actor.state.get("location_id")
            current = projection.entities.get(location_id) if isinstance(location_id, str) else None
            return IntentProposal(
                kind=IntentKind.SEARCH,
                actor_id=actor.id,
                target_id=current.id if current is not None else None,
                target_slug=current.slug if current is not None else None,
                text=cleaned,
            )

        if re.match(r"^(look|observe|examine|inspect|survey|check)\b", normalized):
            return IntentProposal(
                kind=IntentKind.OBSERVE,
                actor_id=actor.id,
                text=cleaned,
            )

        raise UnparsedIntentError(
            "the action did not match a supported intent",
            supported=[
                "move",
                "observe",
                "search",
                "speak",
                "wait",
                "negotiate",
                "engineer",
                "confront",
                "gather",
                "give",
                "abandon",
            ],
        )
