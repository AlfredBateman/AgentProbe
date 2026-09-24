from functools import cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # No env_file: scripts load .env via `uv run --env-file .env`, so unit tests never see it.
    database_url: str | None = None
    encryption_key: SecretStr | None = None
    embedding_dim: int = 768

    # Auth (ADR 0009). jwt_secret is checked at startup, not import, so unit tests import freely.
    jwt_secret: SecretStr | None = None
    jwt_ttl_minutes: int = 15
    refresh_ttl_days: int = 30
    signup_allowed_emails: str = ""  # comma-separated; empty = registration closed
    web_origin: str = "http://localhost:3000"
    cookie_secure: bool = True  # browsers accept Secure cookies on http://localhost

    # Rate limits (token buckets, per minute).
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_per_minute: int = 120  # per API key
    auth_rate_limit_per_minute: int = 10  # per client IP on /auth/register and /auth/login
    redis_url: str = "redis://localhost:6379/0"

    log_level: str = "INFO"

    @property
    def signup_allowlist(self) -> set[str]:
        return {e.strip().lower() for e in self.signup_allowed_emails.split(",") if e.strip()}


@cache
def get_settings() -> Settings:
    return Settings()
