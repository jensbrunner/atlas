"""The Broken Span — M0 structured world fixture.

This is a seed of entities, resources, and intentions, not a single narrative
prompt. M2 expands it with clocks, knowledge tables, and full multi-path play.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from atlas.domain.commands import CreateEntityCommand
from atlas.domain.invariants import apply_commands
from atlas.domain.models import CampaignSettings, EntityKind
from atlas.domain.projection import ProjectionState
from atlas.persistence.orm import CampaignRow
from atlas.persistence.repositories import commit_event_batch, create_campaign

CAMPAIGN_SEED = 20_261_111
DEFAULT_TITLE = "The Broken Span"

_HEALTH_BOUNDS = {"health": {"min": 0, "max": 8}, "stress": {"min": 0, "max": 10}}
_COMMON_BOUNDS = {
    "health": {"min": 0, "max": 10},
    "stress": {"min": 0, "max": 10},
    "supplies": {"min": 0, "max": 99},
    "currency": {"min": 0, "max": 9_999},
}


@dataclass(frozen=True, slots=True)
class SeedResult:
    campaign: CampaignRow
    projection: ProjectionState

    def entity_id(self, slug: str) -> str:
        entity = self.projection.entity_by_slug(slug)
        if entity is None:
            raise KeyError(f"seed has no entity with slug {slug!r}")
        return entity.id


def _location(slug: str, name: str, description: str) -> CreateEntityCommand:
    return CreateEntityCommand(
        kind=EntityKind.LOCATION,
        slug=slug,
        display_name=name,
        static={"description": description},
        state={},
        reason="initial Broken Span location",
    )


def seed_broken_span(
    session: Session,
    *,
    title: str = DEFAULT_TITLE,
    seed: int = CAMPAIGN_SEED,
) -> SeedResult:
    campaign = create_campaign(
        session,
        title=title,
        seed=seed,
        settings=CampaignSettings(
            tone="classic fantasy",
            prose_length="medium",
            mechanics_visibility="on_request",
            hard_avoids=["bell_as_supernatural_omen", "missing_relative_backstory"],
            soft_avoids=["ancient_cult", "haunted_monastery", "isolated_fog_village"],
        ),
    )

    location_commands = [
        _location("town_square", "Market Square", "Cobbles, a dry fountain, and a notice board."),
        _location("flood_gate", "Flood Gate", "New masonry holding back the river."),
        _location("old_bridge", "The Old Bridge", "A giant-built span missing three keystones."),
        _location("quarry", "North Quarry", "A disused cutting with loose scree."),
        _location("workshop", "Engineer's Workshop", "Timber, tools, and stone dust."),
        _location("north_road", "North Road", "The caravan route out of town."),
    ]
    locations = apply_commands(ProjectionState(campaign_id=campaign.id), location_commands)
    location_ids = {entity.slug: entity.id for entity in locations.projection.entities.values()}

    entity_commands = [
        CreateEntityCommand(
            kind=EntityKind.PLAYER_CHARACTER,
            slug="rowan",
            display_name="Rowan",
            static={
                "attributes": {"might": 1, "agility": 1, "insight": 2, "presence": 0},
                "training": {"insight": 1},
                "resource_bounds": _COMMON_BOUNDS,
                "description": "A travelling fixer with a practical streak.",
            },
            state={
                "location_id": location_ids["town_square"],
                "health": 7,
                "stress": 1,
                "supplies": 2,
                "currency": 12,
            },
            reason="initial player character",
        ),
        CreateEntityCommand(
            kind=EntityKind.NPC,
            slug="brannoc",
            display_name="Brannoc the Stone Giant",
            static={
                "attributes": {"might": 3, "agility": 0, "insight": 1, "presence": 1},
                "resource_bounds": {
                    "health": {"min": 0, "max": 14},
                    "stress": {"min": 0, "max": 10},
                },
                "goal": "Recover the three sacred stones before the storm.",
                "constraints": [
                    "Will not knowingly cause the town to drown.",
                    "Will not accept ordinary quarry stone as a substitute.",
                ],
                "negotiation_conditions": {
                    "must_return_stones": True,
                    "accepts_equivalent_sacred_stone": True,
                },
            },
            state={"location_id": location_ids["old_bridge"], "health": 14, "stress": 0},
            reason="initial principal NPC",
        ),
        CreateEntityCommand(
            kind=EntityKind.NPC,
            slug="magistrate_elin",
            display_name="Magistrate Elin",
            static={
                "attributes": {"might": 0, "agility": 0, "insight": 1, "presence": 2},
                "resource_bounds": _HEALTH_BOUNDS,
                "goal": "Keep the flood defenses intact and the town calm.",
                "beliefs": [
                    {
                        "claim": "The three sacred stones are ordinary masonry.",
                        "truth_status": "mistaken",
                    }
                ],
            },
            state={"location_id": location_ids["town_square"], "health": 6, "stress": 2},
            reason="initial town authority",
        ),
        CreateEntityCommand(
            kind=EntityKind.NPC,
            slug="durn_engineer",
            display_name="Durn the Engineer",
            static={
                "attributes": {"might": 1, "agility": 0, "insight": 2, "presence": 0},
                "resource_bounds": _HEALTH_BOUNDS,
                "goal": "Repair the flood gate without weakening it.",
                "knows": ["A suitable replacement stone exists but the workshop lacks it."],
            },
            state={"location_id": location_ids["workshop"], "health": 6, "stress": 1},
            reason="initial technical NPC",
        ),
        CreateEntityCommand(
            kind=EntityKind.NPC,
            slug="vessa_captain",
            display_name="Vessa, Mercenary Captain",
            static={
                "attributes": {"might": 2, "agility": 1, "insight": 1, "presence": 1},
                "resource_bounds": _HEALTH_BOUNDS,
                "goal": "Get paid and keep her company alive.",
                "statements": [
                    {
                        "claim": "The caravan guild has no spare stone.",
                        "truth_status": "intentional_lie",
                    }
                ],
            },
            state={
                "location_id": location_ids["town_square"],
                "health": 8,
                "stress": 1,
                "currency": 4,
            },
            reason="initial mercenary NPC",
        ),
        CreateEntityCommand(
            kind=EntityKind.FACTION,
            slug="town_council",
            display_name="Town Council",
            static={
                "goal": "Preserve the flood defenses and public order.",
                "resources": {"grain": 30, "coin": 80},
            },
            state={},
            reason="initial faction",
        ),
        CreateEntityCommand(
            kind=EntityKind.FACTION,
            slug="caravan_guild",
            display_name="Caravan Guild",
            static={
                "goal": "Keep the north road open and profitable.",
                "resources": {"wagons": 4, "coin": 120},
            },
            state={},
            reason="initial faction",
        ),
        CreateEntityCommand(
            kind=EntityKind.FACTION,
            slug="caravan_guild_secret",
            display_name="Caravan Guild Secret",
            static={
                "gm_only": True,
                "secret_marker": "M0_GM_ONLY_CARAVAN_STONE_SOURCE",
                "text": "The guild knows a suitable sacred stone seam off the north road.",
            },
            state={},
            reason="GM-only seed secret for isolation tests",
        ),
        CreateEntityCommand(
            kind=EntityKind.ITEM,
            slug="sacred_stones",
            display_name="Three Sacred Stones",
            static={"sacred": True, "description": "Giant-cut keystones."},
            state={"location_id": location_ids["flood_gate"], "quantity": 3},
            reason="initial quest objects",
        ),
        CreateEntityCommand(
            kind=EntityKind.ITEM,
            slug="timber_stack",
            display_name="Timber Stack",
            static={"material": "oak"},
            state={"location_id": location_ids["workshop"], "quantity": 6},
            reason="initial repair material",
        ),
        CreateEntityCommand(
            kind=EntityKind.ITEM,
            slug="repair_tools",
            display_name="Repair Tools",
            static={"quality": "serviceable"},
            state={"location_id": location_ids["workshop"], "quantity": 1},
            reason="initial repair equipment",
        ),
    ]

    entities = apply_commands(locations.projection, entity_commands)
    _, committed = commit_event_batch(
        session,
        campaign,
        [*locations.events, *entities.events],
        turn_id=None,
        authority="seed",
        rules_version=campaign.rules_version,
        note="The Broken Span initial fixture",
    )
    return SeedResult(campaign=campaign, projection=committed)
