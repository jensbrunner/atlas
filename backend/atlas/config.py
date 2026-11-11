"""Environment-backed application settings.

All runtime configuration is read from ``ATLAS_*`` environment variables (or a
local ``.env`` file). Model identifiers are configuration, never constants
buried in business logic.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AtlasMode = Literal["offline_test", "local", "balanced", "premium"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ATLAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/atlas.db"
    mode: AtlasMode = "offline_test"
    allow_cloud: bool = False
    monthly_usd_limit: float = Field(default=10.0, ge=0)
    session_usd_limit: float = Field(default=2.0, ge=0)
    request_timeout_seconds: float = Field(default=35.0, gt=0)

    local_ollama_url: str = "http://127.0.0.1:11434"
    local_model: str = "qwen3:8b"
    openai_parser_model: str = "gpt-6-luna"
    openai_narrator_model: str = "gpt-6.1-sol"
    openai_premium_model: str = "gpt-6-astra"
    deepseek_model: str = "deepseek-flash"

    def assert_mode_is_configured(self) -> None:
        """Reject modes this milestone cannot actually serve.

        M0 ships only the deterministic fake provider. Cloud and local model
        modes must fail clearly instead of appearing available and silently
        falling back to a less capable path.
        """
        if self.mode != "offline_test":
            raise ValueError(
                f"ATLAS_MODE={self.mode!r} is not available in M0; "
                "only ATLAS_MODE=offline_test is supported"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
