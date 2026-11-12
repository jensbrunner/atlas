from __future__ import annotations

from pathlib import Path

import pytest

from atlas.config import Settings


def test_defaults_are_offline_and_use_luna(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    assert settings.provider == "fake"
    assert settings.live is False
    assert settings.campaign_model == "gpt-6-luna"
    assert settings.narrator_model == "gpt-6-luna"
    assert settings.world_model == "gpt-6-luna"
    assert settings.auditor_model == "gpt-6-luna"
    settings.validate_provider()


def test_live_calls_require_explicit_opt_in_and_a_key() -> None:
    no_opt_in = Settings(provider="openai", allow_cloud=False, openai_api_key="sk-test")
    with pytest.raises(ValueError, match="opt-in"):
        no_opt_in.validate_provider()

    no_key = Settings(provider="openai", allow_cloud=True, openai_api_key=None)
    with pytest.raises(ValueError, match="ATLAS_OPENAI_API_KEY"):
        no_key.validate_provider()

    ready = Settings(provider="openai", allow_cloud=True, openai_api_key="sk-test")
    ready.validate_provider()
    assert ready.live is True


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown provider"):
        Settings(provider="mystery").validate_provider()
