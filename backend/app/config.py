"""Application settings, read from environment variables (and the repo-root .env)."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- infrastructure ---
    database_url: str = "postgresql+asyncpg://tanport:tanport@localhost:5433/tanport"
    test_database_url: str = "postgresql+asyncpg://tanport:tanport@localhost:5433/tanport_test"
    redis_url: str = "redis://localhost:6379/0"
    test_redis_url: str = "redis://localhost:6379/15"

    # --- providers (empty = not configured) ---
    finnhub_api_key: SecretStr = SecretStr("")
    tiingo_api_key: SecretStr = SecretStr("")
    alphavantage_api_key: SecretStr = SecretStr("")
    bot_api_token: SecretStr = SecretStr("")

    # --- domain defaults ---
    withholding_rate: Decimal = Field(default=Decimal("0.15"), ge=0, le=1)
    big_move_threshold_pct: Decimal = Field(default=Decimal("3"), gt=0)
    display_timezone: str = "Asia/Bangkok"

    # --- LLM / notifications (later phases) ---
    anthropic_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    line_channel_access_token: SecretStr = SecretStr("")
    line_user_id: str = ""

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
