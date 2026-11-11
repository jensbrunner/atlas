"""Provider gateway contracts.

M0 ships only the deterministic fake provider. Real adapters arrive in M3, but
the boundary is fixed now so model output can never write state directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class TextResult:
    content: str
    provider: str
    model_id: str
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None


@dataclass(frozen=True, slots=True)
class StructuredResult[T: BaseModel]:
    value: T
    provider: str
    model_id: str
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None


class ModelGateway(Protocol):
    async def generate_text(
        self,
        role: str,
        messages: list[dict[str, str]],
        *,
        budget: dict[str, Any] | None = None,
    ) -> TextResult: ...

    async def generate_structured(
        self,
        role: str,
        messages: list[dict[str, str]],
        schema: type[T],
        *,
        budget: dict[str, Any] | None = None,
    ) -> StructuredResult[T]: ...


class ModelGatewayError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
