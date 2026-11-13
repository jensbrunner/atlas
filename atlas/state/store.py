from __future__ import annotations

import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from atlas.ids import new_id, slugify
from atlas.state.markdown import build_document, gm_block, parse_document
from atlas.state.schemas import (
    NPC,
    CampaignMeta,
    CampaignSeed,
    CampaignState,
    Character,
    Clock,
    Fact,
    Faction,
    InventoryItem,
    Location,
    Track,
    TurnRecord,
    WorldState,
)

_TURN_KIND_ORDER = {"opening": 0, "player": 1, "world": 2}


class CampaignNotFound(Exception):
    pass


class CampaignStore:
    """Canonical campaign state as markdown files.

    Every write is atomic per file: content is written to a temporary file in the
    same directory and replaced with ``os.replace``. The store has no database.
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # -- paths ---------------------------------------------------------

    def campaign_dir(self, campaign_id: str) -> Path:
        if (
            not campaign_id
            or campaign_id in {".", ".."}
            or "/" in campaign_id
            or "\\" in campaign_id
        ):
            raise CampaignNotFound(campaign_id)
        root = self.data_dir / campaign_id
        if root.resolve().parent != self.data_dir.resolve():
            raise CampaignNotFound(campaign_id)
        return root

    def _require(self, campaign_id: str) -> Path:
        root = self.campaign_dir(campaign_id)
        for name in ("campaign.md", "character.md", "world.md"):
            if not (root / name).is_file():
                raise CampaignNotFound(campaign_id)
        return root

    # -- queries -------------------------------------------------------

    def list_campaigns(self) -> list[CampaignMeta]:
        campaigns: list[CampaignMeta] = []
        for path in sorted(self.data_dir.glob("*/campaign.md")):
            try:
                raw, _ = parse_document(path.read_text(encoding="utf-8"))
                campaigns.append(CampaignMeta.model_validate(raw))
            except Exception:
                continue
        campaigns.sort(key=lambda item: item.created_at, reverse=True)
        return campaigns

    # -- create --------------------------------------------------------

    def create(
        self,
        seed: CampaignSeed,
        *,
        narrator_model: str,
        creative_brief: str = "",
    ) -> CampaignState:
        campaign_id = new_id("cmp")
        root = self.campaign_dir(campaign_id)
        root.mkdir(parents=True, exist_ok=True)
        (root / "npcs").mkdir(exist_ok=True)
        (root / "turns").mkdir(exist_ok=True)

        facts: dict[str, Fact] = {}
        for fact_draft in seed.facts:
            fact_id = fact_draft.id or f"fact_{slugify(fact_draft.text)[:48]}_{len(facts)}"
            facts[fact_id] = Fact(
                id=fact_id,
                text=fact_draft.text,
                visibility=fact_draft.visibility,
                tags=fact_draft.tags,
            )

        locations = {
            slugify(item.id): Location(
                name=item.name,
                description=item.description,
                player_known=item.player_known,
                tags=item.tags,
            )
            for item in seed.locations
        }
        factions = {
            slugify(item.id): Faction(
                name=item.name,
                goal=item.goal,
                stance=item.stance,
                resources=item.resources,
                player_known=item.player_known,
            )
            for item in seed.factions
        }
        clocks = {
            slugify(item.id): Clock(
                name=item.name,
                segments=item.segments,
                filled=min(item.filled, item.segments),
                trigger=item.trigger,
                visibility=item.visibility,
            )
            for item in seed.clocks
        }
        npcs: dict[str, NPC] = {}
        npc_bodies: dict[str, str] = {}
        for npc_draft in seed.npcs:
            npc_id = slugify(npc_draft.id, fallback="npc")
            npcs[npc_id] = NPC(
                id=npc_id,
                name=npc_draft.name,
                location=slugify(npc_draft.location) if npc_draft.location else "",
                player_known=npc_draft.player_known,
                attitude=npc_draft.attitude,
                attributes=npc_draft.attributes,
                skills=npc_draft.skills,
                health=Track(current=npc_draft.health_max, max=npc_draft.health_max),
                goals=npc_draft.goals,
                plans=npc_draft.plans,
                knows=[fact for fact in npc_draft.knows if fact in facts],
            )
            body = npc_draft.appearance.strip()
            if npc_draft.secret.strip():
                body = f"{body}\n\n{gm_block(npc_draft.secret)}".strip()
            npc_bodies[npc_id] = body

        inventory = {
            slugify(item.name): InventoryItem(
                name=item.name,
                quantity=item.quantity,
                tags=item.tags,
                description=item.description,
            )
            for item in seed.character.inventory
        }
        character = Character(
            id=new_id("pc"),
            name=seed.character.name,
            concept=seed.character.concept,
            attributes=seed.character.attributes,
            skills=seed.character.skills,
            health=Track(current=seed.character.health_max, max=seed.character.health_max),
            stress=Track(current=0, max=seed.character.stress_max),
            supplies=seed.character.supplies,
            currency=seed.character.currency,
            conditions=seed.character.conditions,
            inventory=inventory,
        )
        world = WorldState(
            current_location=slugify(seed.current_location),
            situation=seed.premise,
            locations=locations,
            factions=factions,
            clocks=clocks,
            facts=facts,
        )
        meta = CampaignMeta(
            id=campaign_id,
            title=seed.title,
            genre=seed.genre,
            tone=seed.tone,
            premise=seed.premise,
            created_at=datetime.now(UTC),
            narrator_model=narrator_model,
            world_time_minutes=seed.start_minute,
            creative_brief=creative_brief,
        )

        character_body = "\n\n".join(
            part for part in (seed.character.appearance, seed.character.background) if part.strip()
        )
        world_body = seed.notes.strip() or seed.premise.strip()
        state = CampaignState(
            root=root,
            meta=meta,
            character=character,
            world=world,
            npcs=npcs,
            campaign_body=seed.notes,
            character_body=character_body,
            world_body=world_body,
            npc_bodies=npc_bodies,
            journal="",
        )

        self.save(state)
        record = TurnRecord(
            turn=0,
            kind="opening",
            action="Begin the campaign",
            world_time_before=seed.start_minute,
            world_time_after=seed.start_minute,
            model=narrator_model,
            narration=seed.opening_scene.strip(),
        )
        self.append_turn(state, record)
        return state

    # -- load ----------------------------------------------------------

    def load(self, campaign_id: str) -> CampaignState:
        root = self._require(campaign_id)

        raw, campaign_body = parse_document((root / "campaign.md").read_text(encoding="utf-8"))
        meta = CampaignMeta.model_validate(raw)

        char_raw, char_body = parse_document((root / "character.md").read_text(encoding="utf-8"))
        character = Character.model_validate(char_raw)

        world_raw, world_body = parse_document((root / "world.md").read_text(encoding="utf-8"))
        world = WorldState.model_validate(world_raw)

        npcs: dict[str, NPC] = {}
        npc_bodies: dict[str, str] = {}
        for path in sorted((root / "npcs").glob("*.md")):
            npc_raw, npc_body = parse_document(path.read_text(encoding="utf-8"))
            npc = NPC.model_validate(npc_raw)
            npcs[path.stem] = npc
            npc_bodies[path.stem] = npc_body

        journal_path = root / "journal.md"
        journal = journal_path.read_text(encoding="utf-8") if journal_path.exists() else ""

        turns: list[TurnRecord] = []
        for path in sorted((root / "turns").glob("*.md")):
            turn_raw, narration = parse_document(path.read_text(encoding="utf-8"))
            turn_raw["narration"] = narration.strip()
            turns.append(TurnRecord.model_validate(turn_raw))
        turns.sort(key=lambda item: (item.turn, _TURN_KIND_ORDER[item.kind]))

        return CampaignState(
            root=root,
            meta=meta,
            character=character,
            world=world,
            npcs=npcs,
            journal=journal,
            campaign_body=campaign_body,
            character_body=char_body,
            world_body=world_body,
            npc_bodies=npc_bodies,
            turns=turns,
        )

    # -- save ----------------------------------------------------------

    def save(self, state: CampaignState) -> None:
        meta_raw = state.meta.model_dump(mode="json")
        _atomic_write(
            state.root / "campaign.md",
            build_document(meta_raw, state.campaign_body),
        )
        _atomic_write(
            state.root / "character.md",
            build_document(_character_frontmatter(state.character), state.character_body),
        )
        world_raw = state.world.model_dump(mode="json")
        _atomic_write(
            state.root / "world.md",
            build_document(world_raw, state.world_body),
        )

        npc_dir = state.root / "npcs"
        npc_dir.mkdir(exist_ok=True)
        wanted = {f"{slugify(npc_id)}.md" for npc_id in state.npcs}
        for path in npc_dir.glob("*.md"):
            if path.name not in wanted:
                path.unlink()
        for npc_id, npc in state.npcs.items():
            _atomic_write(
                npc_dir / f"{slugify(npc_id)}.md",
                build_document(
                    npc.model_dump(mode="json"),
                    state.npc_bodies.get(npc_id, ""),
                ),
            )

    def append_turn(self, state: CampaignState, record: TurnRecord) -> Path:
        turns_dir = state.root / "turns"
        turns_dir.mkdir(exist_ok=True)
        if record.kind == "world":
            base = f"{record.turn:04d}-world"
            filename = f"{base}.md"
            index = 2
            while (turns_dir / filename).exists():
                filename = f"{base}-{index}.md"
                index += 1
        else:
            filename = f"{record.turn:04d}.md"
        frontmatter = record.model_dump(mode="json", exclude={"narration"})
        path = turns_dir / filename
        _atomic_write(path, build_document(frontmatter, record.narration))

        if record.kind in {"opening", "player"}:
            entry = _journal_entry(record)
            state.journal = f"{state.journal.rstrip()}\n\n{entry}".strip()
            _atomic_write(state.root / "journal.md", f"{state.journal}\n")
        state.turns.append(record)
        return path

    def delete(self, campaign_id: str) -> None:
        root = self._require(campaign_id)
        shutil.rmtree(root)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _character_frontmatter(character: Character) -> dict[str, object]:
    return character.model_dump(mode="json")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def format_world_time(minutes: int) -> str:
    day = minutes // (24 * 60) + 1
    hour = (minutes % (24 * 60)) // 60
    minute = minutes % 60
    return f"Day {day}, {hour:02d}:{minute:02d}"


def time_of_day(minutes: int) -> str:
    hour = (minutes % (24 * 60)) // 60
    if 5 <= hour < 8:
        return "Dawn"
    if 8 <= hour < 12:
        return "Morning"
    if 12 <= hour < 17:
        return "Afternoon"
    if 17 <= hour < 21:
        return "Evening"
    return "Night"


def _journal_entry(record: TurnRecord) -> str:
    title = "Opening" if record.kind == "opening" else f"Turn {record.turn}"
    lines = [
        f"## {title} — {format_world_time(record.world_time_after)}",
        "",
    ]
    if record.action and record.kind == "player":
        lines.append(f"**Action:** {record.action}")
        lines.append("")
    lines.append(record.narration.strip())
    if record.rolls:
        lines.append("")
        for roll in record.rolls:
            check = f" ({roll.check})" if roll.check else ""
            lines.append(
                f"*{roll.label}{check}: {roll.dice[0]}+{roll.dice[1]}"
                f"{roll.modifier:+d} = {roll.total} vs {roll.difficulty} — {roll.outcome}*"
            )
    return "\n".join(lines).strip()
