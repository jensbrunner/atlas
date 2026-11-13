from __future__ import annotations

import secrets
from dataclasses import dataclass

_RANDOM = secrets.SystemRandom()

_SETTINGS = (
    "a settlement built around a shared workshop",
    "a seasonal camp at a trade crossing",
    "a vertical neighborhood built around a stairwell",
    "a large house divided into rented rooms",
    "a remote estate after its owners left",
    "a traveling company between engagements",
    "a hill town above a quarry",
    "a market that moves with the season",
    "a monastery converted into a hospital",
    "a fishing village below a cliff",
    "a stop on a road that is being abandoned",
    "a theater district after the season",
    "a mining camp above the tree line",
    "a university quarter during a recess",
    "a farming cooperative in a dry year",
    "a salvage yard at the edge of a city",
    "a watch post on a quiet border",
    "a commune of artists in a former factory",
    "a pilgrimage hostel in a dry country",
    "a floating market at low tide",
    "a mountain observatory",
    "a caravan halted at a border",
    "a city block after a fire",
    "a forest village built around a single well",
    "a rail depot in a declining town",
    "a court in exile",
    "a boarding school during winter recess",
    "a printing house and its neighborhood",
)

_RELATIONSHIPS = (
    "two siblings",
    "a former mentor and student",
    "co-owners of something fragile",
    "neighbors with an old disagreement",
    "old friends who lost touch",
    "a creditor and debtor",
    "rival craftspeople",
    "a parent and adult child",
    "two people who share a secret",
    "a caretaker and dependent",
    "a performer and patron",
    "two people who used to be married",
    "a local and a newcomer",
    "an apprentice and a master",
    "a buyer and seller",
    "two coworkers",
    "a host and guest",
    "a healer and patient",
    "a landlord and tenant",
    "two people bound by a promise",
    "a leader and a dissenter",
    "an archivist and a claimant",
)

_OPENINGS = (
    "during a shared meal",
    "at the end of a long shift",
    "while waiting for someone who never arrives",
    "during a public ceremony",
    "in the middle of an argument",
    "on the morning after a celebration",
    "while repairing something",
    "at a private negotiation",
    "during a journey's last leg",
    "while moving into a new space",
    "in the middle of a lesson",
    "during a funeral or memorial",
    "while inventorying a storeroom",
    "at a performance rehearsal",
    "during a quiet handover",
    "while searching for a missing object",
    "during bad weather",
    "at the first meeting of a new group",
    "while closing up for the night",
    "during a family argument",
    "at a border check",
    "during an evacuation",
    "in the aftermath of a mistake",
    "while preparing for a guest",
    "at a public announcement",
    "during a private ritual",
    "on a day when nothing is scheduled",
)

_PRESSURES = (
    "a debt comes due",
    "a protected person disappears",
    "a boundary is disputed",
    "a promised shipment is late",
    "a public performance goes wrong",
    "a will is contested",
    "a fire destroys a workshop",
    "a child claims to have seen something impossible",
    "a cure is running out",
    "a letter arrives with the wrong name",
    "a key is missing",
    "a rumor spreads faster than the truth",
    "a favor is called in",
    "a seasonal deadline approaches",
    "a debt is forgiven with strings attached",
    "a rival makes an offer",
    "a trust is broken",
    "a road or route closes",
    "a store is emptied",
    "a promise is broken",
    "someone returns after a long absence",
    "a contract is renegotiated",
    "a discovery changes the value of something",
    "a legal claim is filed",
    "an old agreement expires",
)

_TEXTURES = (
    "cold metal",
    "beeswax",
    "woodsmoke",
    "wet paper",
    "citrus peel",
    "chalk dust",
    "salt",
    "pine resin",
    "old wool",
    "ink",
    "bread",
    "rust",
    "sawdust",
    "lavender",
    "burnt sugar",
    "wet earth",
    "linen",
    "tar",
    "brass",
    "mint",
    "soot",
    "fresh plaster",
    "leather",
    "vinegar",
    "cedar",
    "ozone",
    "melted snow",
    "dye",
    "tea",
    "straw",
)

_WILDCARDS = (
    "a map is out of date",
    "a room is always cold",
    "a door opens outward",
    "an animal follows one person",
    "a borrowed object is returned changed",
    "a song everyone knows but no one can name",
    "a key fits a door that no longer exists",
    "a letter has no sender",
    "a clock runs slow",
    "a mirror is missing",
    "a garden grows out of season",
    "a rumor is written down",
    "a storm leaves something behind",
    "a seat is always kept empty",
    "a path appears where none was",
    "a name is mispronounced by everyone",
    "a room has two doors that lead to the same place",
    "a gift is refused",
    "a debt is paid in an unexpected currency",
    "a public statue is altered",
    "a recipe is missing an ingredient",
    "a tool is repaired with the wrong part",
    "a window faces the wrong direction",
    "a piece of clothing is worn inside out",
    "a message arrives twice",
    "a page is torn from a ledger",
    "a lamp burns without heat",
    "a key is warm",
    "a shadow moves against the light",
    "a mirror fogs from the inside",
    "a floorboard sounds a note",
    "a chair is moved every night",
    "a mark appears on the wall",
    "a coin has the wrong face",
    "a road sign points the wrong way",
    "a letter is dated tomorrow",
    "a bird nests in an odd place",
    "a page is bound out of order",
    "a name is missing from a list",
)

_LENSES = (
    "a small object changes hands",
    "a sound from outside the scene",
    "a smell tied to a particular person or place",
    "a routine task is interrupted",
    "a physical detail triggers a memory",
    "a minor character reacts in a way that complicates the scene",
    "weather changes what movement is possible",
    "a promise or debt is invoked",
    "someone lies by omission",
    "a private moment is observed",
    "a door, route, or object is blocked",
    "a favor is asked for at a bad time",
    "a piece of information is misunderstood",
    "a small act of care costs something",
    "a sound stops unexpectedly",
    "a character changes their mind",
    "a mundane object becomes important",
    "the scene's pace slows for a beat",
    "a public and private version of the same event",
    "an old arrangement no longer fits",
)


@dataclass(frozen=True)
class CreativeBrief:
    setting: str
    relationship: str
    opening: str
    pressure: str
    texture: str
    wildcard: str

    def as_prompt(self) -> str:
        return "\n".join(
            [
                "Creative brief (raw material; build the campaign around it):",
                f"- Setting seed: {self.setting}",
                f"- Relationship seed: {self.relationship}",
                f"- Opening seed: {self.opening}",
                f"- Pressure seed: {self.pressure}",
                f"- Texture seed: {self.texture}",
                f"- Wildcard seed: {self.wildcard}",
                "",
                "Connect at least three of these into one specific situation. "
                "You may reinterpret them, but keep their specificity. Where the "
                "player prompt is already specific, use these as supporting texture "
                "rather than overriding it.",
            ]
        )


def make_creative_brief() -> CreativeBrief:
    """Draw a fresh brief from the OS CSPRNG, not a model or fixed sequence."""

    return CreativeBrief(
        setting=_RANDOM.choice(_SETTINGS),
        relationship=_RANDOM.choice(_RELATIONSHIPS),
        opening=_RANDOM.choice(_OPENINGS),
        pressure=_RANDOM.choice(_PRESSURES),
        texture=_RANDOM.choice(_TEXTURES),
        wildcard=_RANDOM.choice(_WILDCARDS),
    )


def choose_narrative_lens(recent: list[str] | None = None) -> str:
    """Pick a texture for this turn, avoiding the last few used."""

    recent_lenses = [lens for lens in (recent or []) if lens]
    candidates = [lens for lens in _LENSES if lens not in recent_lenses[-4:]]
    return _RANDOM.choice(candidates or list(_LENSES))
