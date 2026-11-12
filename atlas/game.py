from __future__ import annotations

import random
import re
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from atlas.agents.auditor import Auditor
from atlas.agents.campaign import CampaignGenerator, CampaignRequest
from atlas.agents.narrator import Narrator
from atlas.agents.providers import build_provider
from atlas.agents.types import Provider, add_usage
from atlas.agents.world import WorldAgent
from atlas.config import Settings
from atlas.errors import BudgetExceeded, EmptyNarration, LeakDetected
from atlas.state.markdown import extract_gm_block_text
from atlas.state.render import gm_view, player_view
from atlas.state.schemas import CampaignMeta, CampaignState, RollRecord, TurnRecord, Usage
from atlas.state.store import CampaignNotFound, CampaignStore
from atlas.state.validate import validate_state
from atlas.tools.context import ToolContext
from atlas.tools.registry import ToolRegistry, build_default_registry


@dataclass
class TurnResult:
    turn: int
    narration: str
    rolls: list[RollRecord]
    changes: list[str]
    usage: Usage
    world_turn_requested: bool
    world_turn_ran: bool
    player: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "narration": self.narration,
            "rolls": [roll.model_dump(mode="json") for roll in self.rolls],
            "changes": self.changes,
            "usage": self.usage.model_dump(mode="json"),
            "world_turn_requested": self.world_turn_requested,
            "world_turn_ran": self.world_turn_ran,
            "player": self.player,
        }


class CampaignService:
    """Coordinates generation, narration, tools, and text persistence."""

    def __init__(
        self,
        settings: Settings,
        *,
        provider: Provider | None = None,
        store: CampaignStore | None = None,
        registry: ToolRegistry | None = None,
        rng_factory: Callable[[], random.Random] | None = None,
    ) -> None:
        if provider is None:
            settings.validate_provider()
            provider = build_provider(
                provider=settings.provider,
                api_key=settings.openai_api_key,
                timeout=settings.request_timeout_seconds,
                input_usd_per_million=settings.input_usd_per_million,
                output_usd_per_million=settings.output_usd_per_million,
            )
        self.settings = settings
        self.provider = provider
        self.store = store or CampaignStore(settings.data_dir)
        self.registry = registry or build_default_registry()
        self.rng_factory = rng_factory or random.Random
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._create_lock = threading.Lock()
        self._session_usage = Usage()

    # -- queries -------------------------------------------------------

    def list_campaigns(self) -> list[CampaignMeta]:
        return self.store.list_campaigns()

    def get(self, campaign_id: str) -> CampaignState:
        return self.store.load(campaign_id)

    def player(self, campaign_id: str) -> dict[str, Any]:
        return player_view(self.store.load(campaign_id))

    def gm(self, campaign_id: str) -> dict[str, Any]:
        return gm_view(self.store.load(campaign_id))

    def delete(self, campaign_id: str) -> None:
        with self._lock(campaign_id):
            self.store.delete(campaign_id)

    # -- creation ------------------------------------------------------

    def create_campaign(self, request: CampaignRequest) -> tuple[CampaignState, Usage]:
        with self._create_lock:
            generator = CampaignGenerator(self.provider, self.settings)
            seed, usage = generator.generate(
                request,
                avoid_names=self._existing_names(),
            )
            state = self.store.create(seed, narrator_model=self.settings.narrator_model)
            self._account(usage)
            return state, usage

    # -- play ----------------------------------------------------------

    def play_turn(
        self,
        campaign_id: str,
        action: str,
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> TurnResult:
        action = action.strip()
        if not action:
            raise ValueError("action cannot be empty")
        if len(action) > 4_000:
            raise ValueError("action is too long")

        with self._lock(campaign_id):
            state = self.store.load(campaign_id)
            time_before = state.meta.world_time_minutes
            ctx = ToolContext(state=state, rng=self.rng_factory())
            narrator = Narrator(self.provider, self.registry, self.settings)
            reply = narrator.play(state, action, ctx, on_event=on_event)
            total_usage = reply.usage
            self._account(reply.usage)

            narration = reply.text.strip()
            if not narration:
                raise EmptyNarration("narrator returned empty narration")
            try:
                self._check_leaks(state, narration)
            except LeakDetected as leak:
                if on_event is not None:
                    on_event({"type": "status", "stage": "repairing"})
                repaired = narrator.repair(
                    state,
                    action,
                    narration,
                    leak.matched,
                    ctx,
                    on_event=on_event,
                )
                total_usage = add_usage(total_usage, repaired.usage)
                self._account(repaired.usage)
                narration = repaired.text.strip()
                if not narration:
                    raise EmptyNarration(
                        "narrator returned empty narration after leak repair"
                    ) from None
                self._check_leaks(state, narration)
            if on_event is not None:
                on_event({"type": "status", "stage": "saving"})
            validate_state(state)

            turn_no = state.meta.turn_count + 1
            state.meta.turn_count = turn_no
            record = TurnRecord(
                turn=turn_no,
                kind="player",
                action=action,
                world_time_before=time_before,
                world_time_after=state.meta.world_time_minutes,
                model=self.settings.narrator_model,
                usage=total_usage,
                rolls=ctx.rolls,
                changes=ctx.changes,
                narration=narration,
            )
            self.store.save(state)
            self.store.append_turn(state, record)

            world_turn_requested = ctx.world_turn_requested
            world_reason = ""
            if world_turn_requested:
                world_reason = "requested by the narrator"
            else:
                auto, why = self._should_auto_world_turn(state, turn_no)
                if auto:
                    world_reason = why

            world_turn_ran = False
            if world_reason:
                if on_event is not None:
                    on_event({"type": "status", "stage": "world"})
                try:
                    self._world_turn_locked(campaign_id, world_reason)
                    world_turn_ran = True
                except Exception:
                    # A failed offscreen update must not erase a committed player turn.
                    pass

            return TurnResult(
                turn=turn_no,
                narration=narration,
                rolls=ctx.rolls,
                changes=ctx.changes,
                usage=total_usage,
                world_turn_requested=world_turn_requested,
                world_turn_ran=world_turn_ran,
                player=player_view(self.store.load(campaign_id)),
            )

    # -- world ---------------------------------------------------------

    def world_turn(self, campaign_id: str, reason: str = "") -> dict[str, Any]:
        with self._lock(campaign_id):
            return self._world_turn_locked(campaign_id, reason)

    def _world_turn_locked(self, campaign_id: str, reason: str) -> dict[str, Any]:
        state = self.store.load(campaign_id)
        time_before = state.meta.world_time_minutes
        ctx = ToolContext(state=state, rng=self.rng_factory())
        agent = WorldAgent(self.provider, self.registry, self.settings)
        reply = agent.run(state, reason, ctx)
        self._account(reply.usage)
        validate_state(state)
        record = TurnRecord(
            turn=state.meta.turn_count,
            kind="world",
            action=reason or "The world moves on",
            world_time_before=time_before,
            world_time_after=state.meta.world_time_minutes,
            model=self.settings.world_model,
            usage=reply.usage,
            rolls=ctx.rolls,
            changes=ctx.changes,
            narration=reply.text.strip(),
        )
        self.store.save(state)
        self.store.append_turn(state, record)
        return {
            "summary": reply.text.strip(),
            "changes": ctx.changes,
            "rolls": [roll.model_dump(mode="json") for roll in ctx.rolls],
            "usage": reply.usage.model_dump(mode="json"),
            "player": player_view(self.store.load(campaign_id)),
        }

    # -- audit ---------------------------------------------------------

    def audit(self, campaign_id: str) -> dict[str, Any]:
        state = self.store.load(campaign_id)
        auditor = Auditor(self.provider, self.settings)
        findings, usage = auditor.audit(state)
        self._account(usage)
        return {
            "campaign_id": campaign_id,
            "findings": findings,
            "usage": usage.model_dump(mode="json"),
        }

    # -- internals -----------------------------------------------------

    def _should_auto_world_turn(
        self,
        state: CampaignState,
        turn_no: int,
    ) -> tuple[bool, str]:
        if not self.settings.auto_world_turns:
            return False, ""
        last_world = next(
            (turn for turn in reversed(state.turns) if turn.kind == "world"),
            None,
        )
        last_turn = last_world.turn if last_world is not None else 0
        if last_world is not None:
            last_time = last_world.world_time_after
        elif state.turns:
            last_time = state.turns[0].world_time_after
        else:
            last_time = state.meta.world_time_minutes
        turns_since = turn_no - last_turn
        if turns_since >= self.settings.world_turn_interval:
            return True, f"{turns_since} player turns passed"
        minutes_since = state.meta.world_time_minutes - last_time
        if (
            self.settings.world_turn_minutes > 0
            and minutes_since >= self.settings.world_turn_minutes
        ):
            return True, f"{minutes_since} in-world minutes passed"
        return False, ""

    def _existing_names(self, limit: int = 25) -> list[str]:
        names: set[str] = set()
        for meta in self.store.list_campaigns()[:limit]:
            try:
                state = self.store.load(meta.id)
            except Exception:
                continue
            names.add(state.character.name)
            names.update(npc.name for npc in state.npcs.values())
            names.update(location.name for location in state.world.locations.values())
            names.update(faction.name for faction in state.world.factions.values())
        return sorted(name for name in names if name.strip())

    def _lock(self, campaign_id: str) -> threading.Lock:
        return self._locks[campaign_id]

    def _account(self, usage: Usage) -> None:
        self._session_usage = add_usage(self._session_usage, usage)
        cap = self.settings.session_usd_limit
        if cap > 0 and self._session_usage.estimated_usd > cap:
            spent = self._session_usage.estimated_usd
            raise BudgetExceeded(f"session cost limit exceeded: ${spent:.2f} > ${cap:.2f}")

    def _check_leaks(self, state: CampaignState, narration: str) -> None:
        haystack = narration.casefold()
        protected: list[str] = []
        for fact in state.world.facts.values():
            if fact.visibility == "gm" and len(fact.text.strip()) >= 8:
                protected.append(fact.text.strip())
        for body in (state.world_body, *state.npc_bodies.values()):
            blocks = extract_gm_block_text(body)
            for line in blocks.replace("<!-- gm -->", "").replace("<!-- /gm -->", "").splitlines():
                cleaned = line.strip()
                if len(cleaned) >= 12:
                    protected.append(cleaned)

        for secret in protected:
            if secret.casefold() in haystack:
                raise LeakDetected(secret[:80])

        # Names are matched on word boundaries so a hidden "Mara" does not trip
        # on "marathon". Hidden entities should not be named at all.
        hidden_names = [npc.name.strip() for npc in state.npcs.values() if not npc.player_known]
        hidden_names += [
            location.name.strip()
            for location in state.world.locations.values()
            if not location.player_known
        ]
        hidden_names += [
            faction.name.strip()
            for faction in state.world.factions.values()
            if not faction.player_known
        ]
        for name in hidden_names:
            if len(name) < 3:
                continue
            pattern = rf"(?<!\w){re.escape(name)}(?!\w)"
            if re.search(pattern, narration, flags=re.IGNORECASE):
                raise LeakDetected(name[:80])


__all__ = ["CampaignService", "TurnResult", "CampaignNotFound"]
