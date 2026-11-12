from __future__ import annotations

from dataclasses import dataclass, field
from random import Random

from atlas.state.schemas import CampaignState, RollRecord


class ToolError(Exception):
    """A tool call was well-formed JSON but violated a rule or bound."""


@dataclass
class ToolContext:
    state: CampaignState
    rng: Random
    rolls: list[RollRecord] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    world_turn_requested: bool = False
    time_advanced: bool = False

    def note(self, change: str) -> None:
        self.changes.append(change)
