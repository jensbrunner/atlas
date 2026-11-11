"""The Broken Span — structured M2 world fixture.

This is a seed of locations, characters, materials, claims, knowledge links,
relationships, NPC goals, and faction clocks — not a single narrative prompt.
The giant, the town council, and the mercenary captain each hold a different
part of the truth, and the fixture supports negotiation, engineering,
confrontation, restitution, abandonment, and clock-forced failure endings.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from atlas.domain.characters import (
    DEFAULT_TEMPLATE_SLUG,
    get_character_template,
)
from atlas.domain.commands import (
    ChangeRelationshipCommand,
    CreateClockCommand,
    CreateEntityCommand,
    CreateFactCommand,
    DomainCommand,
    LearnStatementCommand,
    RecordStatementCommand,
)
from atlas.domain.invariants import apply_commands
from atlas.domain.models import (
    CampaignSettings,
    EntityKind,
    RelationshipDimension,
    StatementKind,
)
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


def _npc(
    slug: str,
    name: str,
    *,
    location_id: str,
    attributes: dict[str, int],
    training: dict[str, int],
    goal: str,
    plan: str,
    health: int,
    stress: int,
    resource_bounds: dict[str, dict[str, int]] | None = None,
    **extra: object,
) -> CreateEntityCommand:
    return CreateEntityCommand(
        kind=EntityKind.NPC,
        slug=slug,
        display_name=name,
        static={
            "attributes": attributes,
            "training": training,
            "resource_bounds": resource_bounds or _HEALTH_BOUNDS,
            "goal": goal,
            "plan": plan,
            **extra,
        },
        state={"location_id": location_id, "health": health, "stress": stress},
        reason=f"initial NPC: {name}",
    )


def seed_broken_span(
    session: Session,
    *,
    title: str = DEFAULT_TITLE,
    seed: int = CAMPAIGN_SEED,
    template_slug: str = DEFAULT_TEMPLATE_SLUG,
) -> SeedResult:
    template = get_character_template(template_slug)
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

    player_static = template.static_payload()
    player_static["goal"] = "Find a settlement that keeps the town dry and the giant's bargain."
    player_static["plan"] = "Learn who actually knows a source of sacred stone."
    player_state = template.state_payload(location_ids["town_square"])

    entity_commands = [
        CreateEntityCommand(
            kind=EntityKind.PLAYER_CHARACTER,
            slug="rowan",
            display_name="Rowan",
            static=player_static,
            state=player_state,
            reason=f"initial player character from {template.slug} template",
        ),
        _npc(
            "brannoc",
            "Brannoc the Stone Giant",
            location_id=location_ids["old_bridge"],
            attributes={"might": 2, "agility": 0, "insight": 1, "presence": 1},
            training={"confrontation": 2, "negotiation": 0, "engineering": 1, "survival": 1},
            goal="Recover the three sacred keystones before the storm reaches the bridge.",
            plan=(
                "Threaten the town with the bridge's collapse, then accept only true sacred "
                "stone or a shared guardianship."
            ),
            health=14,
            stress=0,
            resource_bounds={
                "health": {"min": 0, "max": 14},
                "stress": {"min": 0, "max": 10},
            },
            constraints=[
                "Will not knowingly cause the town to drown.",
                "Will not accept ordinary quarry stone as a substitute.",
            ],
            negotiation_conditions={
                "must_return_stones": True,
                "accepts_equivalent_sacred_stone": True,
                "accepts_shared_guardianship": True,
            },
        ),
        _npc(
            "magistrate_elin",
            "Magistrate Elin",
            location_id=location_ids["town_square"],
            attributes={"might": 0, "agility": 0, "insight": 1, "presence": 2},
            training={"negotiation": 1, "confrontation": 0, "engineering": 0, "survival": 0},
            goal="Keep the flood defenses intact and the town calm.",
            plan="Deny that the stones are sacred and hold the council together.",
            health=6,
            stress=2,
            beliefs=[
                {
                    "claim": "The three sacred stones are ordinary masonry.",
                    "truth_status": "mistaken",
                }
            ],
        ),
        _npc(
            "durn_engineer",
            "Durn the Engineer",
            location_id=location_ids["workshop"],
            attributes={"might": 1, "agility": 0, "insight": 2, "presence": 0},
            training={"negotiation": 0, "confrontation": 0, "engineering": 2, "survival": 1},
            goal="Repair the flood gate without weakening it.",
            plan="Find fresh-cut stone that answers the old wards and fit it before the storm.",
            health=6,
            stress=1,
        ),
        _npc(
            "vessa_captain",
            "Vessa, Mercenary Captain",
            location_id=location_ids["town_square"],
            attributes={"might": 2, "agility": 1, "insight": 1, "presence": 1},
            training={"negotiation": 1, "confrontation": 2, "engineering": 0, "survival": 1},
            goal="Get paid and keep her company alive.",
            plan="Sell the council protection and keep the guild's stone source quiet.",
            health=8,
            stress=1,
            statements=[
                {
                    "claim": "The caravan guild has no spare stone.",
                    "truth_status": "intentional_lie",
                }
            ],
        ),
        CreateEntityCommand(
            kind=EntityKind.FACTION,
            slug="town_council",
            display_name="Town Council",
            static={
                "goal": "Preserve the flood defenses and public order.",
                "plan": "Deny the stones' significance until a cheaper fix appears.",
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
                "plan": "Avoid committing stone or guards until the road is threatened.",
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
            slug="replacement_stones",
            display_name="Replacement Stones",
            static={
                "material": "sacred-compatible stone",
                "description": "Uncut stone from the north quarry seam.",
            },
            state={"location_id": location_ids["quarry"], "quantity": 6},
            reason="M2 engineering material",
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
            slug="iron_fittings",
            display_name="Iron Fittings",
            static={"material": "iron"},
            state={"location_id": location_ids["workshop"], "quantity": 4},
            reason="M2 engineering material",
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
    ids = {entity.slug: entity.id for entity in entities.projection.entities.values()}

    story_commands: list[DomainCommand] = [
        CreateFactCommand(
            fact_slug="stones_are_sacred_keystones",
            text=(
                "The three stones in the flood gate are giant-cut sacred keystones from "
                "Brannoc's ancestral bridge; fresh sacred-compatible stone can replace them."
            ),
            reason="canonical M2 truth",
        ),
        CreateFactCommand(
            fact_slug="storm_reaches_town",
            text="A major storm reaches Broken Span after roughly twelve hours.",
            reason="canonical M2 truth",
        ),
        RecordStatementCommand(
            statement_slug="brannoc_demands_stones",
            speaker_id=ids["brannoc"],
            proposition=(
                "Brannoc demands the return of all three sacred keystones before the storm."
            ),
            topic="giant_demand",
            kind=StatementKind.CLAIM,
            is_true=True,
            audience_ids=[ids["magistrate_elin"], ids["vessa_captain"], ids["rowan"]],
            reason="public opening demand",
        ),
        RecordStatementCommand(
            statement_slug="brannoc_no_ordinary_stone",
            speaker_id=ids["brannoc"],
            proposition="Brannoc will not accept ordinary quarry stone as a substitute.",
            topic="stone_source",
            kind=StatementKind.CLAIM,
            is_true=True,
            audience_ids=[ids["rowan"]],
            reason="giant's constraint",
        ),
        RecordStatementCommand(
            statement_slug="durn_stone_source",
            speaker_id=ids["durn_engineer"],
            proposition=(
                "A seam of sacred-compatible stone lies in the north quarry; fresh-cut "
                "stones can replace the giant's keystones."
            ),
            topic="stone_source",
            kind=StatementKind.CLAIM,
            is_true=True,
            audience_ids=[],
            reason="actionable engineering lead",
        ),
        RecordStatementCommand(
            statement_slug="elin_stones_are_ordinary",
            speaker_id=ids["magistrate_elin"],
            proposition="The three sacred stones are ordinary masonry.",
            topic="stones_nature",
            kind=StatementKind.MISCONCEPTION,
            is_true=False,
            audience_ids=[ids["rowan"]],
            reason="NPC misconception",
        ),
        RecordStatementCommand(
            statement_slug="vessa_no_spare_stone",
            speaker_id=ids["vessa_captain"],
            proposition="There is no spare sacred stone anywhere near Broken Span.",
            topic="stone_source",
            kind=StatementKind.LIE,
            is_true=False,
            audience_ids=[ids["rowan"]],
            reason="intentionally dishonest statement",
        ),
        LearnStatementCommand(
            entity_id=ids["rowan"],
            statement_slug="brannoc_demands_stones",
            source="public_demand",
            reason="the demand is public knowledge",
        ),
        ChangeRelationshipCommand(
            from_id=ids["magistrate_elin"],
            to_id=ids["rowan"],
            dimension=RelationshipDimension.TRUST,
            delta=1,
            reason="the magistrate tolerates the fixer",
        ),
        ChangeRelationshipCommand(
            from_id=ids["durn_engineer"],
            to_id=ids["rowan"],
            dimension=RelationshipDimension.TRUST,
            delta=1,
            reason="Durn respects practical help",
        ),
        ChangeRelationshipCommand(
            from_id=ids["vessa_captain"],
            to_id=ids["rowan"],
            dimension=RelationshipDimension.TRUST,
            delta=-1,
            reason="Vessa does not trust outsiders",
        ),
        CreateClockCommand(
            clock_slug="storm_arrival",
            name="Storm Arrival",
            segments=6,
            filled=0,
            trigger=(
                "The storm floods the lower town. The flood gate fails and the council's "
                "authority collapses."
            ),
            visibility="PUBLIC",
            reason="storm timeline",
        ),
        CreateClockCommand(
            clock_slug="giant_deadline",
            name="Brannoc's Patience",
            segments=4,
            filled=0,
            trigger="Brannoc tears down the old bridge and seals the north road.",
            owner_id=ids["brannoc"],
            visibility="PUBLIC",
            reason="giant escalation",
        ),
        CreateClockCommand(
            clock_slug="town_unrest",
            name="Town Unrest",
            segments=4,
            filled=0,
            trigger="The town turns on the council and takes the stones by force.",
            owner_id=ids["town_council"],
            visibility="PUBLIC",
            reason="civil order",
        ),
    ]

    story = apply_commands(entities.projection, story_commands)
    _, committed = commit_event_batch(
        session,
        campaign,
        [*locations.events, *entities.events, *story.events],
        turn_id=None,
        authority="seed",
        rules_version=campaign.rules_version,
        note="The Broken Span M2 fixture",
    )
    return SeedResult(campaign=campaign, projection=committed)
