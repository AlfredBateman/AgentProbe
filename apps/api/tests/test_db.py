import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.models import User
from apitest import leftover_tables

pytestmark = pytest.mark.integration


async def test_test_database_is_reachable(db: AsyncSession) -> None:
    assert (await db.execute(text("SELECT 1"))).scalar_one() == 1


async def test_vector_extension_installed(db: AsyncSession) -> None:
    result = await db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    assert result.scalar_one_or_none() == 1


async def test_leftover_rows_are_detected(db: AsyncSession) -> None:
    conn = await db.connection()
    assert await leftover_tables(conn) == []
    db.add(User(email="leftover@example.com", password_hash="fake"))
    await db.flush()
    assert await leftover_tables(conn) == ["users"]
