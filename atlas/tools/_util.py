from __future__ import annotations

from atlas.tools.context import ToolError


def as_int(value: object, default: int = 0) -> int:
    """Coerce a model-supplied JSON value to an int, raising a tool error."""

    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ToolError(f"expected an integer, got {value!r}") from exc
    raise ToolError(f"expected an integer, got {type(value).__name__}")


def as_bool(value: object, default: bool = False) -> bool:
    """Coerce a model-supplied JSON value to a bool, raising a tool error."""

    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    raise ToolError(f"expected a boolean, got {value!r}")
