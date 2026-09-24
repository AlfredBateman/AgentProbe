"""Token-bucket rate limiting. In-memory by default, Redis for multi-process deployments."""

import math
import time
from collections.abc import Callable
from typing import Protocol

from redis.asyncio import Redis


class RateLimiter(Protocol):
    async def acquire(self, bucket: str) -> float | None:
        """Take one token from `bucket`. None if allowed, else seconds until a token is free."""
        ...


class MemoryTokenBucket:
    """Per-process buckets. The event loop is single-threaded and acquire() never awaits,
    so each call is atomic without a lock.
    """

    # ponytail: per-process state; N workers each allow the full rate. Use RedisTokenBucket then.
    _MAX_BUCKETS = 10_000

    def __init__(self, per_minute: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0  # tokens per second
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}  # bucket -> (tokens, updated_at)

    async def acquire(self, bucket: str) -> float | None:
        now = self._clock()
        tokens, updated = self._buckets.get(bucket, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - updated) * self.rate)
        if tokens < 1:
            self._buckets[bucket] = (tokens, now)
            return (1 - tokens) / self.rate
        self._buckets[bucket] = (tokens - 1, now)
        if len(self._buckets) > self._MAX_BUCKETS:
            self._prune(now)
        return None

    def _prune(self, now: float) -> None:
        # A bucket that has refilled to capacity is indistinguishable from a missing one.
        full_after = self.capacity / self.rate
        self._buckets = {k: v for k, v in self._buckets.items() if now - v[1] < full_after}


# KEYS[1] = bucket key; ARGV = capacity, rate (tokens/s). Uses Redis' clock, so app servers'
# clock skew doesn't matter. Returns 0 if allowed, else milliseconds until the next token.
_LUA = """
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1e6
local state = redis.call('HMGET', KEYS[1], 'tokens', 'updated')
local tokens = tonumber(state[1]) or capacity
local updated = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + (now - updated) * rate)
local wait = 0
if tokens < 1 then
  wait = math.ceil((1 - tokens) / rate * 1000)
else
  tokens = tokens - 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', now)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / rate) + 1)
return wait
"""


class RedisTokenBucket:
    def __init__(self, redis: Redis, per_minute: int, *, prefix: str = "ratelimit:") -> None:
        self.capacity = per_minute
        self.rate = per_minute / 60.0
        self._prefix = prefix
        self._script = redis.register_script(_LUA)

    async def acquire(self, bucket: str) -> float | None:
        wait_ms = int(
            await self._script(keys=[self._prefix + bucket], args=[self.capacity, self.rate])
        )
        return wait_ms / 1000 if wait_ms else None


def retry_after_header(seconds: float) -> str:
    return str(max(1, math.ceil(seconds)))
