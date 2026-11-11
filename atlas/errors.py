from __future__ import annotations


class AtlasError(Exception):
    """Base class for errors that map to a typed API response."""


class LeakDetected(AtlasError):
    """Narration contained material the player must not see."""

    def __init__(self, matched: str) -> None:
        # Never echo the protected text back to the client.
        super().__init__("narration contained protected GM material")
        self.matched = matched


class EmptyNarration(AtlasError):
    pass


class BudgetExceeded(AtlasError):
    pass
