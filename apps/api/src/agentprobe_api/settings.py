from functools import cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
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
    signup_open: bool = False  # true: any email may register (a public demo, ADR 0035)
    web_origin: str = "http://localhost:3000"
    cookie_secure: bool = True  # browsers accept Secure cookies on http://localhost
    # The web app's server-side proxy sends this along with the browser's IP in
    # x-agentprobe-client-ip (ADR 0036). Only a request carrying it has that IP trusted;
    # everything else is keyed by the connecting address.
    proxy_secret: SecretStr | None = None
    # Hosts that sleep when idle and expose GET /health (the demo agents on a free tier,
    # ADR 0036): a run or connection test against one wakes it first. Comma-separated.
    wake_target_hosts: str = ""
    # Set by Render to the deployed commit; /ready reports it for the deploy workflow.
    render_git_commit: str | None = None

    # Public-deploy caps (docs/DEPLOY.md). None = unlimited, for local and self-hosted use.
    max_signups_per_day: int | None = None  # all users, rolling 24 h
    max_projects_per_user: int | None = None
    max_agents_per_user: int | None = None
    max_cases_per_suite: int | None = None
    max_runs_per_user_per_day: int | None = None  # rolling 24 h, server runs and CI reports
    # Worst-case live (non-mock) LLM spend per rolling 24 h across all users. Each live run
    # reserves 2 x LLM_BUDGET_USD_PER_RUN (its judges' client and its clustering client).
    llm_global_usd_per_day: float | None = None

    # Rate limits (token buckets, per minute).
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_per_minute: int = 120  # per API key
    auth_rate_limit_per_minute: int = 10  # per client IP on /auth/register and /auth/login
    register_rate_limit_per_hour: int = 20  # per client IP on /auth/register, on top of that
    connection_test_rate_limit_per_minute: int = 20  # per account, both test-connection routes
    redis_url: str = "redis://localhost:6379/0"

    # Runs (ADR 0017). inline: runs execute in the API process (local dev, `pnpm verify`);
    # redis: one Taskiq job per attempt on Redis, executed by `agentprobe_api.worker`.
    queue_backend: Literal["inline", "redis"] = "inline"
    inline_max_runs: int = 2  # runs executing at once in the API process
    run_concurrency: int = 4  # attempts in flight per run (inline)
    run_max_retries: int = 2  # per attempt, for unreachable agents only
    run_backoff_base_s: float = 1.0
    run_stale_after_s: int = 600  # a queued/running run this quiet is resumed on startup

    # Base URL of the deployed dashboard, used for links in PR comments and exports.
    # None: dashboard_url in responses is omitted.
    public_web_url: str | None = None

    log_level: str = "INFO"

    @field_validator("web_origin")
    @classmethod
    def _bare_origin(cls, value: str) -> str:
        """Browsers send Origin as exactly scheme://host[:port], never with a trailing slash,
        and the Origin check and the SSE CORS header compare to it exactly. So a URL copied
        with its trailing slash is reduced to that form, and one with a path, query, fragment
        or credentials refuses to load.
        """
        url = urlsplit(value.strip())
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username is not None
            or url.path not in ("", "/")
            or url.query
            or url.fragment
        ):
            raise ValueError(f"WEB_ORIGIN must be scheme://host[:port], got {value!r}")
        return f"{url.scheme}://{url.netloc.lower()}"

    @property
    def signup_allowlist(self) -> set[str]:
        return {e.strip().lower() for e in self.signup_allowed_emails.split(",") if e.strip()}

    @property
    def wake_hosts(self) -> set[str]:
        return {h.strip().lower() for h in self.wake_target_hosts.split(",") if h.strip()}


@cache
def get_settings() -> Settings:
    return Settings()
