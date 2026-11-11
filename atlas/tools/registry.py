from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from atlas.tools.character import handle_patch_character
from atlas.tools.clocks import handle_create_clock, handle_patch_clock
from atlas.tools.context import ToolContext, ToolError
from atlas.tools.dice import handle_roll
from atlas.tools.facts import handle_append_journal, handle_record_fact, handle_reveal_fact
from atlas.tools.inventory import handle_patch_inventory
from atlas.tools.npcs import handle_update_faction, handle_update_npc
from atlas.tools.time import handle_advance_time
from atlas.tools.world import handle_request_world_turn, handle_set_scene

ToolHandler = Callable[[ToolContext, dict[str, Any]], str]

_ATTRIBUTE_ENUM = ["might", "agility", "insight", "presence"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="roll",
        description=(
            "Roll 2d6 plus an attribute and optional skill against a difficulty. "
            "Use only when the outcome is uncertain and failure matters."
        ),
        parameters=_object(
            {
                "label": {"type": "string", "description": "What is being attempted."},
                "attribute": {"type": "string", "enum": _ATTRIBUTE_ENUM},
                "skill": {"type": "string", "description": "Optional trained skill."},
                "difficulty": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 20,
                    "description": "Target number. 8 is routine, 10 hard, 12 severe.",
                },
                "modifier": {
                    "type": "integer",
                    "minimum": -5,
                    "maximum": 5,
                    "description": "Situational bonus or penalty.",
                },
            },
            ["label", "attribute", "difficulty"],
        ),
        handler=handle_roll,
    ),
    ToolSpec(
        name="patch_character",
        description=(
            "Adjust the player character's health, stress, supplies, currency, or conditions."
        ),
        parameters=_object(
            {
                "health_delta": {"type": "integer"},
                "stress_delta": {"type": "integer"},
                "supplies_delta": {"type": "integer"},
                "currency_delta": {"type": "integer"},
                "add_condition": {"type": "string"},
                "remove_condition": {"type": "string"},
            },
            [],
        ),
        handler=handle_patch_character,
    ),
    ToolSpec(
        name="patch_inventory",
        description="Add, remove, or set the quantity of an item the player character carries.",
        parameters=_object(
            {
                "operation": {"type": "string", "enum": ["add", "remove", "set"]},
                "name": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 0},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            ["operation", "name", "quantity"],
        ),
        handler=handle_patch_inventory,
    ),
    ToolSpec(
        name="patch_clock",
        description="Advance or reduce a named clock. Clocks are pressure trackers, not dice.",
        parameters=_object(
            {
                "clock": {"type": "string"},
                "delta": {"type": "integer", "minimum": -20, "maximum": 20},
                "reason": {"type": "string"},
            },
            ["clock", "delta"],
        ),
        handler=handle_patch_clock,
    ),
    ToolSpec(
        name="create_clock",
        description="Create a new clock when a new long-running pressure becomes relevant.",
        parameters=_object(
            {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "segments": {"type": "integer", "minimum": 1, "maximum": 20},
                "trigger": {"type": "string"},
                "visibility": {"type": "string", "enum": ["gm", "player"]},
            },
            ["id", "name", "segments"],
        ),
        handler=handle_create_clock,
    ),
    ToolSpec(
        name="advance_time",
        description="Advance in-world time by a positive number of minutes.",
        parameters=_object(
            {
                "minutes": {"type": "integer", "minimum": 1},
                "reason": {"type": "string"},
            },
            ["minutes"],
        ),
        handler=handle_advance_time,
    ),
    ToolSpec(
        name="update_npc",
        description="Change an NPC's location, attitude, goals, health, or knowledge.",
        parameters=_object(
            {
                "npc": {"type": "string"},
                "location": {"type": "string"},
                "attitude": {"type": "string"},
                "add_goal": {"type": "string"},
                "add_knowledge": {"type": "string"},
                "health_delta": {"type": "integer"},
            },
            ["npc"],
        ),
        handler=handle_update_npc,
    ),
    ToolSpec(
        name="update_faction",
        description="Change a faction's goal, stance, or a named resource.",
        parameters=_object(
            {
                "faction": {"type": "string"},
                "goal": {"type": "string"},
                "stance": {"type": "string"},
                "resource": {"type": "string"},
                "resource_delta": {"type": "integer"},
            },
            ["faction"],
        ),
        handler=handle_update_faction,
    ),
    ToolSpec(
        name="record_fact",
        description=(
            "Record a canonical fact. Use visibility 'gm' for secrets and 'player' for "
            "things the player has learned or can observe."
        ),
        parameters=_object(
            {
                "text": {"type": "string"},
                "visibility": {"type": "string", "enum": ["gm", "player"]},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            ["text", "visibility"],
        ),
        handler=handle_record_fact,
    ),
    ToolSpec(
        name="reveal_fact",
        description="Reveal a previously recorded GM fact to the player.",
        parameters=_object({"fact": {"type": "string"}}, ["fact"]),
        handler=handle_reveal_fact,
    ),
    ToolSpec(
        name="append_journal",
        description="Append a short player-facing journal entry.",
        parameters=_object(
            {
                "text": {"type": "string"},
                "heading": {"type": "string"},
            },
            ["text"],
        ),
        handler=handle_append_journal,
    ),
    ToolSpec(
        name="set_scene",
        description=(
            "Move the scene to a known location and optionally update its "
            "description or the situation."
        ),
        parameters=_object(
            {
                "location": {"type": "string"},
                "description": {"type": "string"},
                "situation": {"type": "string"},
            },
            ["location"],
        ),
        handler=handle_set_scene,
    ),
    ToolSpec(
        name="request_world_turn",
        description="Ask for an offscreen world evolution after this turn is committed.",
        parameters=_object({"reason": {"type": "string"}}, []),
        handler=handle_request_world_turn,
    ),
]


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec] | None = None) -> None:
        self._specs = {spec.name: spec for spec in (specs or SPECS)}

    def names(self) -> list[str]:
        return sorted(self._specs)

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            }
            for spec in self._specs.values()
        ]

    def execute(self, ctx: ToolContext, name: str, args: dict[str, Any]) -> str:
        spec = self._specs.get(name)
        if spec is None:
            return f"ERROR: unknown tool {name!r}"
        try:
            return spec.handler(ctx, args)
        except ToolError as exc:
            return f"ERROR: {exc}"
        except (TypeError, ValueError, KeyError) as exc:
            return f"ERROR: invalid arguments for {name}: {exc}"


def build_default_registry() -> ToolRegistry:
    return ToolRegistry()
