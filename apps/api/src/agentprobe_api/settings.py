from functools import cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # No env_file: scripts load .env via `uv run --env-file .env`, so unit tests never see it.
    database_url: str | None = None
    encryption_key: SecretStr | None = None
    embedding_dim: int = 768


@cache
def get_settings() -> Settings:
    return Settings()
