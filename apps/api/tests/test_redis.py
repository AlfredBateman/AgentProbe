import os

import pytest
from redis.asyncio import Redis


@pytest.mark.redis
async def test_redis_answers_ping() -> None:
    client = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    try:
        assert await client.ping()
    finally:
        await client.aclose()
