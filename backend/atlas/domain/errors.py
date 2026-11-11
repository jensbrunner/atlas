"""Typed domain errors that map to stable API error codes."""

from __future__ import annotations


class DomainError(Exception):
    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, "details": self.details}


class InvariantViolation(DomainError):
    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(f"invariant.{code}", message, **details)


class NotFoundError(DomainError):
    def __init__(self, message: str, **details: object) -> None:
        super().__init__("not_found", message, **details)


class VersionConflictError(DomainError):
    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            "version_conflict",
            f"campaign version changed: expected {expected}, actual {actual}",
            expected=expected,
            actual=actual,
        )


class TurnPendingError(DomainError):
    def __init__(self, turn_id: str) -> None:
        super().__init__(
            "turn_pending",
            "an action with this client id is still being processed",
            turn_id=turn_id,
        )


class InvalidTurnPlanError(DomainError):
    def __init__(self, message: str, **details: object) -> None:
        super().__init__("invalid_turn_plan", message, **details)
