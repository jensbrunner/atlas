from __future__ import annotations

from dataclasses import dataclass

PRICING_UPDATED = "2026-11-12"

PRICING_SOURCES = {
    "openai": "https://developers.openai.com/api/docs/pricing",
    "anthropic": "https://platform.claude.com/docs/en/about-claude/pricing",
    "google": "https://ai.google.dev/gemini-api/docs/pricing",
    "xai": "https://docs.x.ai/developers/pricing",
    "deepseek": "https://api-docs.deepseek.com/quick_start/pricing/",
    "mistral": "https://docs.mistral.ai/getting-started/models/models_overview/",
    "cohere": "https://cohere.com/pricing",
}


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float
    provider: str
    note: str = ""


@dataclass(frozen=True)
class PriceQuote:
    model: str
    input_per_million: float
    output_per_million: float
    provider: str
    source: str
    note: str
    known: bool


def _price(
    input_per_million: float,
    output_per_million: float,
    provider: str,
    note: str = "",
) -> ModelPrice:
    return ModelPrice(input_per_million, output_per_million, provider, note)


# Standard text rates in USD per 1M tokens, checked 2026-11-12.
# Promotional and long-context rates are called out in notes; the table uses
# the standard short-context rate so estimates stay conservative and predictable.
PRICES: dict[str, ModelPrice] = {
    # OpenAI
    "gpt-6.1-sol": _price(2.00, 10.00, "openai"),
    "gpt-6-sol": _price(2.00, 10.00, "openai"),
    "gpt-6-luna": _price(0.10, 0.50, "openai"),
    "gpt-6-astra": _price(10.00, 50.00, "openai"),
    "gpt-6.1-terra": _price(1.00, 5.00, "openai"),
    "gpt-5.6-sol": _price(4.00, 20.00, "openai", "Previous generation."),
    "gpt-5.6-luna": _price(0.20, 1.20, "openai", "Previous generation."),
    "gpt-5.5-pro": _price(30.00, 180.00, "openai", "Pro tier."),
    "gpt-4.1": _price(2.00, 8.00, "openai"),
    "gpt-4o": _price(2.50, 10.00, "openai"),
    "o3": _price(2.00, 8.00, "openai"),
    "o3-mini": _price(1.10, 4.40, "openai"),
    "o4-mini": _price(1.10, 4.40, "openai"),
    # Anthropic
    "claude-fable-5-1": _price(10.00, 50.00, "anthropic"),
    "claude-fable-5-2": _price(8.00, 40.00, "anthropic"),
    "claude-opus-5-5": _price(4.00, 20.00, "anthropic"),
    "claude-opus-5": _price(5.00, 25.00, "anthropic"),
    "claude-sonnet-5-5": _price(2.00, 10.00, "anthropic"),
    "claude-sonnet-5": _price(2.00, 10.00, "anthropic"),
    "claude-sonnet-4-6": _price(3.00, 15.00, "anthropic"),
    "claude-opus-4-8": _price(5.00, 25.00, "anthropic"),
    "claude-haiku-5-5": _price(0.10, 0.50, "anthropic", "Prompt over 100k tokens: $0.50 / $2.50."),
    "claude-haiku-4-5": _price(1.00, 5.00, "anthropic"),
    # Google
    "gemini-4-argon": _price(
        2.00, 10.00, "google", "Intro rate through 2026-11-30; $4 / $20 after."
    ),
    "gemini-4-carbon": _price(
        2.00, 10.00, "google", "Intro rate through 2026-11-30; $4 / $20 after."
    ),
    "gemini-3.8-flash": _price(
        0.75, 3.75, "google", "Intro rate through 2026-12-31; $1.50 / $7.50 after."
    ),
    "gemini-3.6-flash": _price(
        0.75, 3.75, "google", "Intro rate through 2026-12-31; $1.50 / $7.50 after."
    ),
    "gemini-3.5-flash-lite": _price(0.30, 2.50, "google"),
    "gemini-3.1-pro": _price(2.00, 12.00, "google", "Prompts over 200k tokens: $4 / $18."),
    "gemini-3.1-flash-lite": _price(0.25, 1.50, "google"),
    "gemini-3-flash": _price(0.50, 3.00, "google"),
    "gemini-2.5-pro": _price(1.25, 10.00, "google", "Prompts over 200k tokens: $2.50 / $15."),
    "gemini-2.5-flash": _price(0.30, 2.50, "google"),
    "gemini-2.5-flash-lite": _price(0.10, 0.40, "google"),
    # xAI
    "grok-4.7": _price(2.00, 6.00, "xai", "Prompts at or above 200k tokens: $4 / $12."),
    "grok-4.6": _price(2.00, 6.00, "xai", "Prompts at or above 200k tokens: $4 / $12."),
    "grok-4.5": _price(2.00, 6.00, "xai", "Prompts at or above 200k tokens: $4 / $12."),
    "grok-4.3": _price(1.25, 2.50, "xai", "Prompts at or above 200k tokens: $2.50 / $5."),
    "grok-4.20": _price(1.25, 2.50, "xai", "Prompts at or above 200k tokens: $2.50 / $5."),
    "grok-build-0.1": _price(1.00, 2.00, "xai"),
    # DeepSeek: peak rates, so estimates are conservative; off-peak is half.
    "deepseek-flash": _price(0.30, 1.20, "deepseek", "Peak rate; off-peak is $0.15 / $0.60."),
    "deepseek-v4-pro": _price(1.32, 3.96, "deepseek", "Peak rate; off-peak is $0.66 / $1.98."),
    # Mistral
    "mistral-large-4": _price(1.36, 4.18, "mistral"),
    "mistral-large-3": _price(0.50, 1.50, "mistral"),
    "mistral-medium-3.5": _price(1.50, 7.50, "mistral"),
    "mistral-small-4": _price(0.15, 0.60, "mistral"),
    # Cohere
    "command-a": _price(2.50, 10.00, "cohere"),
    "command-a-plus": _price(0.30, 1.50, "cohere", "List price varies by account."),
    "command-r": _price(0.15, 0.60, "cohere"),
    "command-r7b": _price(0.0375, 0.15, "cohere"),
}

ALIASES = {
    "deepseek-v4.1-flash": "deepseek-flash",
    "deepseek-v4-pro-0813": "deepseek-v4-pro",
    "grok-4.20-0309": "grok-4.20",
    "grok-4.20-0309-reasoning": "grok-4.20",
    "grok-4.20-0309-non-reasoning": "grok-4.20",
    "grok-4.20-multi-agent-0309": "grok-4.20",
}


def _normalize(model: str) -> str:
    return model.strip().casefold().replace("_", "-")


_NORMALIZED_PRICES = {_normalize(key): key for key in PRICES}
_NORMALIZED_ALIASES = {_normalize(key): value for key, value in ALIASES.items()}


def _resolve_key(model: str) -> str | None:
    normalized = _normalize(model)
    if normalized in _NORMALIZED_ALIASES:
        normalized = _normalize(_NORMALIZED_ALIASES[normalized])
    if normalized in _NORMALIZED_PRICES:
        return _NORMALIZED_PRICES[normalized]
    for key in sorted(_NORMALIZED_PRICES, key=len, reverse=True):
        if normalized.startswith(key + "-") or normalized.startswith(key + "@"):
            return _NORMALIZED_PRICES[key]
    return None


def price_for(
    model: str,
    *,
    fallback_input: float = 0.0,
    fallback_output: float = 0.0,
) -> PriceQuote | None:
    key = _resolve_key(model)
    if key is not None:
        price = PRICES[key]
        return PriceQuote(
            model=key,
            input_per_million=price.input_per_million,
            output_per_million=price.output_per_million,
            provider=price.provider,
            source=PRICING_SOURCES[price.provider],
            note=price.note,
            known=True,
        )
    if fallback_input > 0 or fallback_output > 0:
        return PriceQuote(
            model=model,
            input_per_million=fallback_input,
            output_per_million=fallback_output,
            provider="custom",
            source="custom fallback",
            note="No built-in list price for this model.",
            known=False,
        )
    return None


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    fallback_input: float = 0.0,
    fallback_output: float = 0.0,
) -> tuple[float, PriceQuote | None]:
    quote = price_for(
        model,
        fallback_input=fallback_input,
        fallback_output=fallback_output,
    )
    if quote is None:
        return 0.0, None
    cost = (
        input_tokens / 1_000_000 * quote.input_per_million
        + output_tokens / 1_000_000 * quote.output_per_million
    )
    return round(cost, 6), quote


def all_prices() -> dict[str, ModelPrice]:
    return dict(PRICES)
