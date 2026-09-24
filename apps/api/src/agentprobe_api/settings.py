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

    # Runs (ADR 0017). inline: runs execute in the API process (local dev, `pnpm verify`);
    # redis: one Taskiq job per attempt on Redis, executed by `agentprobe_api.worker`.
    queue_backend: Literal["inline", "redis"] = "inline"
    inline_max_runs: int = 2  # runs executing at once in the API process
    run_concurrency: int = 4  # attempts in flight per run (inline)
    run_max_retries: int = 2  # per attempt, for unreachable agents only
    run_backoff_base_s: float = 1.0
    run_stale_after_s: int = 600  # a queued/running run this quiet is resumed on startup

    # Base URL of the deployed dashboard, used for links in PR comments and exports
    # (SPEC.md §4.11-4.12). None: dashboard_url in responses is omitted.
    public_web_url: str | None = None

    log_level: str = "INFO"

    @property
    def signup_allowlist(self) -> set[str]:
        return {e.strip().lower() for e in self.signup_allowed_emails.split(",") if e.strip()}


@cache
def get_settings() -> Settings:
    return Settings()
