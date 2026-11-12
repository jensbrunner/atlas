from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Literal

from atlas.state.schemas import CampaignState

DocKind = Literal["npc", "location", "faction", "fact", "clock"]
ContextMode = Literal["narrator", "world", "audit"]

_TOKEN = re.compile(r"[^\W_][\w'-]*", re.UNICODE)
_STOPWORDS = frozenset(
    """
    a an and are as at be been but by for from had has have he her his i if in
    into is it its me my no not of on or our she so that the their them then
    there these they this to was we were what when where which who why will with
    you your
    """.split()
)

_MODE_LIMITS: dict[ContextMode, dict[str, int]] = {
    "narrator": {
        "npc": 6,
        "location": 4,
        "faction": 4,
        "fact": 12,
        "clock": 6,
    },
    "world": {
        "npc": 10,
        "location": 6,
        "faction": 6,
        "fact": 20,
        "clock": 10,
    },
    "audit": {
        "npc": 14,
        "location": 8,
        "faction": 8,
        "fact": 30,
        "clock": 12,
    },
}


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in _TOKEN.findall(text.casefold())
        if len(token) > 1 and token not in _STOPWORDS
    ]


@dataclass(frozen=True)
class Doc:
    kind: DocKind
    id: str
    name: str
    text: str
    location: str = ""
    knows: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass
class Selection:
    npcs: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    factions: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    clocks: list[str] = field(default_factory=list)
    query: str = ""
    totals: dict[str, int] = field(default_factory=dict)

    def count(self, kind: str) -> int:
        return len(getattr(self, _PLURAL[kind]))

    def packet_line(self) -> str:
        parts = []
        for kind in ("npc", "location", "faction", "fact", "clock"):
            selected = self.count(kind)
            total = self.totals.get(kind, selected)
            parts.append(f"{selected}/{total} {_PLURAL[kind]}")
        return ", ".join(parts)


_PLURAL = {
    "npc": "npcs",
    "location": "locations",
    "faction": "factions",
    "fact": "facts",
    "clock": "clocks",
}


class RetrievalIndex:
    """A derived BM25 index over the canonical campaign state.

    Markdown remains the source of truth. The index is cheap to rebuild and
    exists only to choose a small, relevant context packet.
    """

    K1 = 1.5
    B = 0.75

    def __init__(self, state: CampaignState) -> None:
        self.state = state
        self.docs: list[Doc] = []
        self.postings: dict[str, dict[int, int]] = {}
        self.lengths: list[int] = []
        self.doc_ids: dict[tuple[str, str], int] = {}
        self.totals: dict[str, int] = {}
        self._build()

    def _add(self, doc: Doc) -> None:
        index = len(self.docs)
        self.docs.append(doc)
        self.doc_ids[(doc.kind, doc.id)] = index
        tokens = tokenize(doc.text)
        self.lengths.append(len(tokens))
        for token in tokens:
            postings = self.postings.setdefault(token, {})
            postings[index] = postings.get(index, 0) + 1
        self.totals[doc.kind] = self.totals.get(doc.kind, 0) + 1

    def _build(self) -> None:
        state = self.state
        for npc_id, npc in state.npcs.items():
            known_text = " ".join(
                state.world.facts[fact].text for fact in npc.knows if fact in state.world.facts
            )
            body = state.npc_bodies.get(npc_id, "")
            self._add(
                Doc(
                    kind="npc",
                    id=npc_id,
                    name=npc.name,
                    text=" ".join(
                        [
                            npc_id,
                            npc.name,
                            npc.attitude,
                            npc.location,
                            " ".join(npc.goals),
                            " ".join(npc.plans),
                            known_text,
                            body,
                        ]
                    ),
                    location=npc.location,
                    knows=tuple(npc.knows),
                )
            )

        for location_id, location in state.world.locations.items():
            self._add(
                Doc(
                    kind="location",
                    id=location_id,
                    name=location.name,
                    text=" ".join(
                        [location_id, location.name, location.description, " ".join(location.tags)]
                    ),
                    tags=tuple(location.tags),
                )
            )

        for faction_id, faction in state.world.factions.items():
            self._add(
                Doc(
                    kind="faction",
                    id=faction_id,
                    name=faction.name,
                    text=" ".join(
                        [
                            faction_id,
                            faction.name,
                            faction.goal,
                            faction.stance,
                            " ".join(f"{key} {value}" for key, value in faction.resources.items()),
                        ]
                    ),
                )
            )

        for clock_id, clock in state.world.clocks.items():
            self._add(
                Doc(
                    kind="clock",
                    id=clock_id,
                    name=clock.name,
                    text=" ".join([clock_id, clock.name, clock.trigger]),
                )
            )

        for fact_id, fact in state.world.facts.items():
            self._add(
                Doc(
                    kind="fact",
                    id=fact_id,
                    name=fact.text[:80],
                    text=" ".join([fact_id, fact.text, " ".join(fact.tags)]),
                    tags=tuple(fact.tags),
                )
            )

        self.avgdl = (sum(self.lengths) / len(self.lengths)) if self.lengths else 1.0

    def search(
        self,
        query: str,
        *,
        kind: DocKind | None = None,
        limit: int = 8,
    ) -> list[tuple[float, Doc]]:
        query_tokens = set(tokenize(query))
        if not query_tokens:
            return []

        scores: dict[int, float] = {}
        total_docs = len(self.docs)
        for token in query_tokens:
            postings = self.postings.get(token)
            if not postings:
                continue
            idf = math.log(1 + (total_docs - len(postings) + 0.5) / (len(postings) + 0.5))
            for index, frequency in postings.items():
                doc = self.docs[index]
                if kind is not None and doc.kind != kind:
                    continue
                length = self.lengths[index]
                denominator = frequency + self.K1 * (1 - self.B + self.B * length / self.avgdl)
                score = idf * frequency * (self.K1 + 1) / denominator
                scores[index] = scores.get(index, 0.0) + score

        query_phrase = " ".join(tokenize(query))
        for index in list(scores):
            name = self.docs[index].name.casefold()
            if name and (name in query_phrase or query_phrase in name):
                scores[index] += 8.0

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [(score, self.docs[index]) for index, score in ranked[:limit]]

    def get(self, kind: DocKind, doc_id: str) -> Doc | None:
        index = self.doc_ids.get((kind, doc_id))
        return self.docs[index] if index is not None else None


def _qualified(
    index: RetrievalIndex,
    query: str,
    *,
    kind: DocKind,
    limit: int,
) -> list[Doc]:
    matches = index.search(query, kind=kind, limit=limit)
    if not matches:
        return []
    cutoff = max(2.0, matches[0][0] * 0.35)
    return [doc for score, doc in matches if score >= cutoff]


def _unique(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    if limit <= 0:
        return result
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def select_context(
    state: CampaignState,
    action: str,
    *,
    mode: ContextMode = "narrator",
) -> Selection:
    index = RetrievalIndex(state)
    limits = _MODE_LIMITS[mode]
    world = state.world
    selection = Selection(totals=dict(index.totals))

    present_ids = [
        npc_id for npc_id, npc in state.npcs.items() if npc.location == world.current_location
    ]

    current_location = world.locations.get(world.current_location)
    if current_location is not None:
        selection.locations.append(world.current_location)

    query_parts = [action]
    if current_location is not None:
        query_parts.extend([current_location.name, current_location.description])
    if state.turns:
        query_parts.append(state.turns[-1].narration[:1_500])
    query = "\n".join(part for part in query_parts if part.strip())
    selection.query = query

    selection.npcs = []
    for doc in _qualified(
        index,
        query,
        kind="npc",
        limit=limits["npc"] * 2,
    ):
        if len(selection.npcs) >= limits["npc"]:
            break
        if doc.id not in selection.npcs:
            selection.npcs.append(doc.id)

    for npc_id in present_ids:
        if len(selection.npcs) >= limits["npc"]:
            break
        if npc_id not in selection.npcs:
            selection.npcs.append(npc_id)

    if len(selection.npcs) < limits["npc"]:
        for doc in _qualified(
            index,
            query,
            kind="npc",
            limit=limits["npc"] * 2,
        ):
            if doc.id not in selection.npcs:
                selection.npcs.append(doc.id)
            if len(selection.npcs) >= limits["npc"]:
                break

    if len(selection.locations) < limits["location"]:
        for doc in _qualified(
            index,
            query,
            kind="location",
            limit=limits["location"] + len(selection.locations),
        ):
            if doc.id not in selection.locations:
                selection.locations.append(doc.id)
            if len(selection.locations) >= limits["location"]:
                break

    for doc in _qualified(
        index,
        query,
        kind="faction",
        limit=limits["faction"],
    ):
        if doc.id not in selection.factions:
            selection.factions.append(doc.id)
        if len(selection.factions) >= limits["faction"]:
            break

    for doc in _qualified(
        index,
        query,
        kind="clock",
        limit=limits["clock"],
    ):
        if doc.id not in selection.clocks:
            selection.clocks.append(doc.id)
        if len(selection.clocks) >= limits["clock"]:
            break

    # A present scene should include facts its people know.
    fact_limit = limits["fact"]
    known: list[str] = []
    for npc_id in selection.npcs:
        npc = state.npcs.get(npc_id)
        if npc is not None:
            known.extend(npc.knows)

    # Action-relevant facts come first; known facts fill the remaining slots.
    selected_facts: list[str] = []
    for doc in _qualified(
        index,
        query,
        kind="fact",
        limit=fact_limit + len(known),
    ):
        if doc.id not in selected_facts:
            selected_facts.append(doc.id)
        if len(selected_facts) >= fact_limit:
            break
    for fact_id in known:
        if len(selected_facts) >= fact_limit:
            break
        if fact_id in world.facts and fact_id not in selected_facts:
            selected_facts.append(fact_id)
    selection.facts = selected_facts

    # Clocks with pressure are more important than empty ones.
    active = [clock_id for clock_id, clock in world.clocks.items() if clock.filled > 0]
    selection.clocks = _unique(active + selection.clocks, limits["clock"])

    # Keep locations of selected NPCs available for continuity.
    for npc_id in selection.npcs:
        npc = state.npcs.get(npc_id)
        if npc is not None and npc.location and npc.location not in selection.locations:
            if len(selection.locations) < limits["location"]:
                selection.locations.append(npc.location)

    return selection
