import os

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.db import CONNECT_ARGS, normalize_url
from agentprobe_api.models import Base

pytestmark = pytest.mark.integration


def test_downgrade_upgrade_round_trip(migrated: None, alembic_config: Config) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


def test_models_match_migrations(migrated: None) -> None:
    engine = create_engine(
        normalize_url(os.environ["TEST_DATABASE_URL"]), connect_args=CONNECT_ARGS
    )
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"compare_type": True})
            assert compare_metadata(ctx, Base.metadata) == []
    finally:
        engine.dispose()


async def test_every_foreign_key_is_indexed(db: AsyncSession) -> None:
    # An FK is covered when some index on its table leads with the FK column.
    unindexed = await db.execute(
        text(
            """
            SELECT c.conrelid::regclass::text || '.' || a.attname
            FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
            WHERE c.contype = 'f'
              AND c.connamespace = 'public'::regnamespace
              AND NOT EXISTS (
                SELECT 1 FROM pg_index i
                WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1]
              )
            """
        )
    )
    assert unindexed.scalars().all() == []


async def test_runs_indexed_by_suite_and_created_at(db: AsyncSession) -> None:
    result = await db.execute(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_runs_suite_id_created_at'")
    )
    assert "(suite_id, created_at)" in result.scalar_one()
