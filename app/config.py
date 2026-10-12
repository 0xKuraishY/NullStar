"""Runtime configuration, read once from the environment."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Nullstar"
    app_tagline: str = "Cybersecurity GitHub discovery radar"

    database_url: str = "sqlite:///./data/nullstar.sqlite3"
    secret_key: str = "insecure-dev-key-change-me"

    github_token: str = ""
    github_api: str = "https://api.github.com"

    scheduler_enabled: bool = True
    collect_interval_minutes: int = 60

    # Rolling mode: instead of one hourly batch, cycle a couple of sources every
    # ninety seconds so the wire is never more than minutes stale and the API
    # quota is spent evenly instead of in one burst.
    rolling_enabled: bool = True
    rolling_interval_seconds: int = 90
    rolling_batch_size: int = 2
    stream_poll_seconds: int = 4
    collect_lookback_days: int = 10
    max_api_calls_per_run: int = 900

    cookie_secure: bool = False
    session_ttl_hours: int = 720
    login_max_attempts: int = 8
    login_lockout_minutes: int = 15

    alert_webhook_url: str = ""
    alert_min_score: int = 80

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
