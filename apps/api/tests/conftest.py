"""Integration fixtures. The root conftest has already refused unsafe DB env by the time
any of these run, and they only connect when an `integration` test requests them.

Isolation (ADR 0008): one connection per session; each test runs inside a transaction
that is rolled back. The session joins it via savepoints, so code under test can commit.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from agentprobe_api.db import make_engine

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


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
