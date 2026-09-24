import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Callable

import pytest
from redis.asyncio import Redis

from agentprobe_api.ratelimit import (
    MemoryTokenBucket,
    RateLimiter,
    RedisTokenBucket,
    retry_after_header,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_memory_bucket_allows_capacity_then_limits() -> None:
    clock = FakeClock()
    limiter = MemoryTokenBucket(60, clock=clock)  # 1 token/s, burst 60
    assert all([await limiter.acquire("k") is None for _ in range(60)])
    retry = await limiter.acquire("k")
    assert retry is not None and 0 < retry <= 1


async def test_memory_bucket_refills_over_time() -> None:
    clock = FakeClock()
    limiter = MemoryTokenBucket(60, clock=clock)
    for _ in range(60):
        await limiter.acquire("k")
    assert await limiter.acquire("k") is not None
    clock.now += 1.0
    assert await limiter.acquire("k") is None
    assert await limiter.acquire("k") is not None


async def test_memory_bucket_prunes_full_buckets() -> None:
    clock = FakeClock()
    limiter = MemoryTokenBucket(60, clock=clock)
    limiter._MAX_BUCKETS = 3
    for name in "abcd":
        await limiter.acquire(name)
    clock.now += 61  # every bucket has refilled
    await limiter.acquire("e")
    await limiter.acquire("f")
    await limiter.acquire("g")
    await limiter.acquire("h")
    assert set(limiter._buckets) <= {"e", "f", "g", "h"}


def test_retry_after_is_whole_seconds_at_least_one() -> None:
    assert retry_after_header(0.01) == "1"
    assert retry_after_header(1.2) == "2"


# --- behaviour shared by both implementations -------------------------------------------

MakeLimiter = Callable[[int], RateLimiter]


@pytest.fixture(
    params=["memory", pytest.param("redis", marks=pytest.mark.redis)],
)
async def make_limiter(request: pytest.FixtureRequest) -> AsyncIterator[MakeLimiter]:
    redis = None
    if request.param == "redis":
        redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        prefix = f"test:{uuid.uuid4()}:"

    def make(per_minute: int) -> RateLimiter:
        if redis is not None:
            return RedisTokenBucket(redis, per_minute, prefix=prefix)
        return MemoryTokenBucket(per_minute)

    yield make
    if redis is not None:
        await redis.aclose()


async def test_limits_after_burst(make_limiter: MakeLimiter) -> None:
    limiter = make_limiter(3)
    assert [await limiter.acquire("k") for _ in range(3)] == [None, None, None]
    retry = await limiter.acquire("k")
    assert retry is not None and 0 < retry <= 20  # 3/min -> one token every 20 s


async def test_buckets_are_independent(make_limiter: MakeLimiter) -> None:
    limiter = make_limiter(1)
    assert await limiter.acquire("a") is None
    assert await limiter.acquire("a") is not None
    assert await limiter.acquire("b") is None


async def test_refills_in_real_time(make_limiter: MakeLimiter) -> None:
    limiter = make_limiter(600)  # 10 tokens/s
    # Drain until denied (tokens keep refilling while the loop runs).
    for _ in range(1000):
        if await limiter.acquire("k") is not None:
            break
    else:
        pytest.fail("bucket never ran dry")
    await asyncio.sleep(0.25)
    assert await limiter.acquire("k") is None
