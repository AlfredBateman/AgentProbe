"""API test fixtures. The root conftest has already refused unsafe DB env by the time any
DB fixture runs, and they only connect when an `integration` test requests them.

Isolation (ADR 0008): one connection per session; each test runs inside a transaction
that is rolled back. The session joins it via savepoints, so code under test can commit.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from agentprobe_api.db import make_engine
from agentprobe_api.main import create_app
from apitest import ClientFactory, SignUp, bind_db, client_for, make_settings, signed_up

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"
# --- integration fixtures ---------------------------------------------------------------


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["url"] = os.environ["TEST_DATABASE_URL"]
    cfg.attributes["skip_logging_config"] = True
    return cfg


@pytest.fixture(scope="session")
def migrated(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")


@pytest.fixture(scope="session")
async def engine(migrated: None) -> AsyncIterator[AsyncEngine]:
    engine = make_engine(os.environ["TEST_DATABASE_URL"])  # same config as production
    yield engine
    await engine.dispose()


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest.fixture
def app(db: AsyncSession) -> FastAPI:
    return bind_db(create_app(make_settings()), db)


@pytest.fixture
async def clients(app: FastAPI) -> AsyncIterator[ClientFactory]:
    opened: list[httpx.AsyncClient] = []

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        opened.append(client_for(app, **kwargs))
        return opened[-1]

    yield factory
    for c in opened:
        await c.aclose()


@pytest.fixture
def sign_up(clients: ClientFactory) -> SignUp:
    """sign_up("alice@example.com") -> a client holding alice's session cookies."""

    async def go(email: str) -> httpx.AsyncClient:
        return await signed_up(clients(), email)

    return go
