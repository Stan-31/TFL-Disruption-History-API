from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    environment: Literal["local", "ci", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    tfl_app_key: str
    database_url: PostgresDsn

    tfl_poll_interval_seconds: int = 60
    tfl_modes: str = "tube,overground,dlr,elizabeth-line,bus"

    api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
