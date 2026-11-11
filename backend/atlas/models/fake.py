"""Deterministic, network-free model gateway for tests and offline mode."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from typing import Any

from pydantic import BaseModel, ValidationError

from atlas.models.interfaces import (
    ModelGatewayError,
    StructuredResult,
    T,
    TextResult,
)


class FakeModelGateway:
    """Scripted provider.

    Text calls return queued responses when available, otherwise a stable digest
    marker. Structured calls require a queued response: silently inventing a
    structured business object would hide contract bugs.
    """

    provider = "fake"

    def __init__(
        self,
        *,
        text_responses: dict[str, list[str]] | None = None,
        structured_responses: dict[str, list[BaseModel | dict[str, Any] | str]] | None = None,
        model_id: str = "fake-deterministic",
    ) -> None:
        self.model_id = model_id
        self._text: dict[str, deque[str]] = defaultdict(deque)
        self._structured: dict[str, deque[BaseModel | dict[str, Any] | str]] = defaultdict(deque)
        for role, text_values in (text_responses or {}).items():
            self._text[role].extend(text_values)
        for role, structured_values in (structured_responses or {}).items():
            self._structured[role].extend(structured_values)
        self.calls: list[tuple[str, str]] = []

    def _digest(self, messages: list[dict[str, str]]) -> str:
        canonical = json.dumps(messages, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    async def generate_text(
        self,
        role: str,
        messages: list[dict[str, str]],
        *,
        budget: dict[str, Any] | None = None,
    ) -> TextResult:
        del budget
        self.calls.append(("text", role))
        if self._text[role]:
            content = self._text[role].popleft()
        else:
            content = f"[fake:{role}:{self._digest(messages)}]"
        return TextResult(
            content=content,
            provider=self.provider,
            model_id=self.model_id,
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
        )

    async def generate_structured(
        self,
        role: str,
        messages: list[dict[str, str]],
        schema: type[T],
        *,
        budget: dict[str, Any] | None = None,
    ) -> StructuredResult[T]:
        del budget
        self.calls.append(("structured", role))
        if not self._structured[role]:
            raise ModelGatewayError(
                "fake_missing_response",
                f"no scripted structured response for role {role!r}",
            )
        raw = self._structured[role].popleft()
        try:
            if isinstance(raw, schema):
                value = raw
            elif isinstance(raw, BaseModel):
                value = schema.model_validate(raw.model_dump(mode="json"))
            elif isinstance(raw, str):
                value = schema.model_validate_json(raw)
            else:
                value = schema.model_validate(raw)
        except ValidationError as exc:
            raise ModelGatewayError(
                "fake_invalid_response",
                f"scripted response for {role!r} failed schema validation: {exc.errors()}",
            ) from exc
        return StructuredResult(
            value=value,
            provider=self.provider,
            model_id=self.model_id,
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
        )
