from __future__ import annotations

from atlas.pricing import (
    PRICES,
    PRICING_SOURCES,
    PRICING_UPDATED,
    estimate_cost,
    price_for,
)


def test_builtin_prices_for_major_models() -> None:
    luna = price_for("gpt-6-luna")
    assert luna is not None
    assert (luna.input_per_million, luna.output_per_million) == (0.10, 0.50)
    assert luna.provider == "openai"

    cases = {
        "claude-sonnet-5-5": (2.0, 10.0, "anthropic"),
        "gemini-3.8-flash": (0.75, 3.75, "google"),
        "grok-4.7": (2.0, 6.0, "xai"),
        "deepseek-flash": (0.30, 1.20, "deepseek"),
        "mistral-large-3": (0.50, 1.50, "mistral"),
        "command-a": (2.50, 10.0, "cohere"),
    }
    for model, (input_rate, output_rate, provider) in cases.items():
        quote = price_for(model)
        assert quote is not None
        assert quote.input_per_million == input_rate
        assert quote.output_per_million == output_rate
        assert quote.provider == provider


def test_cost_math_and_custom_fallback() -> None:
    cost, quote = estimate_cost("gpt-6-luna", 1_000_000, 1_000_000)
    assert cost == 0.60
    assert quote is not None and quote.known

    fallback, custom = estimate_cost(
        "house-model",
        1_000_000,
        500_000,
        fallback_input=2.0,
        fallback_output=4.0,
    )
    assert fallback == 4.0
    assert custom is not None and custom.known is False
    assert custom.source == "custom fallback"


def test_date_suffix_and_alias_resolution() -> None:
    dated = price_for("gpt-6-luna-2026-11-12")
    assert dated is not None and dated.model == "gpt-6-luna"

    alias = price_for("deepseek-v4.1-flash")
    assert alias is not None and alias.model == "deepseek-flash"


def test_unknown_model_without_fallback_is_unpriced() -> None:
    assert price_for("house-model") is None
    cost, quote = estimate_cost("house-model", 1_000, 1_000)
    assert cost == 0.0
    assert quote is None


def test_every_price_has_a_source_and_positive_rate() -> None:
    for model, price in PRICES.items():
        assert price.input_per_million > 0, model
        assert price.output_per_million > 0, model
        assert price.provider in PRICING_SOURCES, model
    assert PRICING_UPDATED == "2026-11-12"
