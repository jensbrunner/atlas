from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration. All live-model use is explicit opt-in."""

    model_config = SettingsConfigDict(
        env_prefix="ATLAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("campaigns")
    provider: str = "fake"

    openai_api_key: str | None = None
    allow_cloud: bool = False

    campaign_model: str = "gpt-6-luna"
    narrator_model: str = "gpt-6-luna"
    world_model: str = "gpt-6-luna"
    auditor_model: str = "gpt-6-luna"

    turn_token_limit: int = Field(default=12_000, ge=1_000)
    max_tool_iterations: int = Field(default=8, ge=1, le=32)
    recent_turn_limit: int = Field(default=6, ge=0, le=50)
    context_char_budget: int = Field(default=48_000, ge=4_000)

    monthly_usd_limit: float = Field(default=10.0, ge=0)
    session_usd_limit: float = Field(default=2.0, ge=0)

    request_timeout_seconds: float = Field(default=90.0, gt=0)

    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def live(self) -> bool:
        return self.provider == "openai"

    def validate_provider(self) -> None:
        if self.provider not in {"fake", "openai"}:
            raise ValueError(f"unknown provider {self.provider!r}; expected 'fake' or 'openai'")
        if self.provider == "openai":
            if not self.allow_cloud:
                raise ValueError(
                    "live model calls are opt-in: set ATLAS_ALLOW_CLOUD=true "
                    "to use the OpenAI provider"
                )
            if not self.openai_api_key:
                raise ValueError("ATLAS_OPENAI_API_KEY is required when ATLAS_PROVIDER=openai")
