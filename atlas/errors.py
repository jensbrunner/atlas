from __future__ import annotations


class AtlasError(Exception):
    """Base class for errors that map to a typed API response."""


class LeakDetected(AtlasError):
    """Narration contained material the player must not see."""

    def __init__(self, matched: str) -> None:
        super().__init__(f"narration contains protected material: {matched!r}")
        self.matched = matched


class EmptyNarration(AtlasError):
    pass


class BudgetExceeded(AtlasError):
    pass
