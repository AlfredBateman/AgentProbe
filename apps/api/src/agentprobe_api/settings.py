from functools import cache
from ipaddress import IPv4Network, IPv6Network, ip_network
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
    signup_open: bool = False  # true: any email may register (a public demo, ADR 0035)
    web_origin: str = "http://localhost:3000"
    cookie_secure: bool = True  # browsers accept Secure cookies on http://localhost
    # The web app's server-side proxy sends this with the browser's IP (ADR 0035). Only a
    # request carrying it has that IP trusted; everything else is keyed by the TCP peer.
    proxy_secret: SecretStr | None = None
    # A header the hosting platform's own proxy sets to the client it accepted the connection
    # from (Fly-Client-IP on Fly.io), trusted only from FORWARDED_ALLOW_IPS peers. Run uvicorn
    # with --no-proxy-headers then, so the peer checked here is the real TCP peer (ADR 0035).
    client_ip_header: str | None = None
    forwarded_allow_ips: str = "127.0.0.1"  # comma-separated IPs or CIDRs, as uvicorn reads it

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

    @property
    def trusted_proxies(self) -> list[IPv4Network | IPv6Network]:
        entries = [n.strip() for n in self.forwarded_allow_ips.split(",") if n.strip()]
        if "*" in entries:  # uvicorn's "trust everyone"
            return [ip_network("0.0.0.0/0"), ip_network("::/0")]
        return [ip_network(n) for n in entries]


@cache
def get_settings() -> Settings:
    return Settings()
