from __future__ import annotations

from collections import deque
from typing import Any

from atlas.agents.types import AgentReply, AgentRequest, StructuredRequest
from atlas.state.schemas import Usage

DEFAULT_NARRATION = (
    "The moment holds. Somewhere nearby a door closes, and the world waits for your next move."
)


class FakeProvider:
    """Deterministic provider for offline development and tests.

    Replies are a queue of :class:`AgentReply` objects. When the queue is empty
    the provider returns a short fixed narration. Campaign generation returns a
    generic fixture that is only used when no seed is supplied.
    """

    def __init__(
        self,
        *,
        replies: list[AgentReply] | None = None,
        campaign_seed: dict[str, Any] | None = None,
        audit_findings: list[dict[str, str]] | None = None,
        default_text: str = DEFAULT_NARRATION,
    ) -> None:
        self.replies: deque[AgentReply] = deque(replies or [])
        self.campaign_seed = campaign_seed
        self.audit_findings = audit_findings or []
        self.default_text = default_text
        self.requests: list[AgentRequest] = []
        self.structured_requests: list[StructuredRequest] = []

    def complete(self, request: AgentRequest) -> AgentReply:
        self.requests.append(request)
        if self.replies:
            return self.replies.popleft()
        return AgentReply(text=self.default_text)

    def generate_structured(self, request: StructuredRequest) -> tuple[dict[str, Any], Usage]:
        self.structured_requests.append(request)
        if request.tool_name == "submit_campaign":
            if self.campaign_seed is not None:
                return self.campaign_seed, Usage()
            return default_seed(request.user_input), Usage()
        if request.tool_name == "submit_audit":
            return {"findings": self.audit_findings}, Usage()
        raise AssertionError(f"unexpected structured tool {request.tool_name}")


def default_seed(prompt: str) -> dict[str, Any]:
    """A small generic campaign used only by the fake provider."""

    cleaned = _prompt_line(prompt)
    title = _title_from(cleaned)
    premise = cleaned or "A traveler arrives in a town with an unresolved problem."
    return {
        "title": title,
        "genre": "fantasy",
        "tone": "grounded, character-driven, a little wry",
        "premise": premise,
        "notes": "",
        "opening_scene": (
            "Rain has been falling since dawn. You come in through the east gate "
            "with mud to the ankle and a letter you have not opened. The square is "
            "half empty, and the people who are still out watch you the way they "
            "watch weather."
        ),
        "current_location": "market_square",
        "character": {
            "name": "Ren",
            "concept": "A wandering fixer with more nerve than sense",
            "attributes": {"might": 0, "agility": 1, "insight": 2, "presence": 1},
            "skills": {"negotiation": 1, "survival": 1},
            "health_max": 7,
            "stress_max": 10,
            "supplies": 2,
            "currency": 12,
            "conditions": [],
            "inventory": [
                {"name": "Travel cloak", "quantity": 1, "tags": ["clothing"]},
                {"name": "Rope", "quantity": 1, "tags": ["tool"]},
                {"name": "Rations", "quantity": 3, "tags": ["food"]},
            ],
            "appearance": "Weathered, watchful, and used to being underestimated.",
            "background": "You take work that other people would rather not name.",
        },
        "locations": [
            {
                "id": "market_square",
                "name": "Market Square",
                "description": "A wide square of cracked flagstones, half-flooded by rain.",
                "player_known": True,
            },
            {
                "id": "harbor",
                "name": "The Harbor",
                "description": "A working harbor with too few boats and too much rope.",
                "player_known": True,
            },
            {
                "id": "council_hall",
                "name": "Council Hall",
                "description": "A stone building with shuttered windows and a locked side door.",
                "player_known": False,
            },
        ],
        "factions": [
            {
                "id": "town_council",
                "name": "The Town Council",
                "goal": "Keep the harbor open through the storm season",
                "stance": "cautious",
                "resources": {"coin": 60, "influence": 3},
                "player_known": True,
            }
        ],
        "clocks": [
            {
                "id": "storm_arrival",
                "name": "Storm Arrival",
                "segments": 6,
                "filled": 0,
                "trigger": "The storm closes the harbor and cuts the town off.",
                "visibility": "player",
            },
            {
                "id": "council_panic",
                "name": "Council Panic",
                "segments": 4,
                "filled": 1,
                "trigger": "The council starts making arrests.",
                "visibility": "gm",
            },
        ],
        "facts": [
            {
                "id": "fact_hidden_debt",
                "text": "The council borrowed heavily against harbor fees that no longer exist.",
                "visibility": "gm",
                "tags": ["secret", "politics"],
            },
            {
                "id": "fact_storm_warning",
                "text": "A storm is expected within two days.",
                "visibility": "player",
                "tags": ["weather"],
            },
        ],
        "npcs": [
            {
                "id": "mara",
                "name": "Mara the Keeper",
                "location": "market_square",
                "player_known": True,
                "attitude": "wary",
                "attributes": {"might": 0, "agility": 0, "insight": 2, "presence": 2},
                "skills": {"negotiation": 2},
                "health_max": 6,
                "goals": ["Find out who has been reading the harbor ledger"],
                "knows": ["fact_hidden_debt", "fact_storm_warning"],
                "appearance": "A compact woman in a waxed coat, always drying her hands.",
                "secret": "Mara has already copied the falsified ledger page and hidden it.",
            }
        ],
    }


def _prompt_line(prompt: str) -> str:
    for line in prompt.splitlines():
        if line.lower().startswith("prompt:"):
            return line.split(":", 1)[1].strip()
    return " ".join(prompt.strip().split())


def _title_from(prompt: str) -> str:
    cleaned = " ".join(prompt.strip().split())
    if not cleaned or cleaned.lower() == "invent a fresh campaign.":
        return "The Quiet Harbor"
    stop = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "with",
        "in",
        "on",
        "at",
        "to",
        "for",
        "from",
        "by",
        "about",
        "where",
        "when",
        "that",
        "which",
        "after",
        "before",
        "while",
    }
    words = cleaned.split(" ")[:8]
    cut = len(words)
    for index in range(1, len(words)):
        if words[index].lower().strip(".,;:!?") in stop:
            cut = index
            break
    return " ".join(words[:cut]).rstrip(".,;:!?").title()
