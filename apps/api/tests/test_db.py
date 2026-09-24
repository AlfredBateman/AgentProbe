import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_test_database_is_reachable(db: AsyncSession) -> None:
    assert (await db.execute(text("SELECT 1"))).scalar_one() == 1


async def test_vector_extension_installed(db: AsyncSession) -> None:
    result = await db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    assert result.scalar_one_or_none() == 1
