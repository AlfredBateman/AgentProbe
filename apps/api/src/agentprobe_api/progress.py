"""Run progress events for SSE (ADR 0017): one `ProgressBus` interface, in-process for the
inline backend and Redis pub/sub for the Redis backend (the worker publishes, the API
process that holds the SSE connection subscribes).

Events carry ids, statuses and counts only, never agent output.
"""

import asyncio
import json
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol

from redis.asyncio import Redis

Event = dict[str, Any]


class Subscription(Protocol):
    async def next(self, wait_s: float) -> Event | None:
        """The next event, or None when `wait_s` seconds pass without one."""
        ...


class ProgressBus(Protocol):
    async def publish(self, run_id: uuid.UUID, event: Event) -> None: ...

    def subscribe(self, run_id: uuid.UUID) -> AbstractAsyncContextManager[Subscription]: ...

    async def aclose(self) -> None: ...


class _QueueSubscription:
    def __init__(self) -> None:
        # ponytail: unbounded; a run has at most 10,000 attempts (500 cases x 20 runs).
        self.queue: asyncio.Queue[Event] = asyncio.Queue()

    async def next(self, wait_s: float) -> Event | None:
        try:
            return await asyncio.wait_for(self.queue.get(), wait_s)
        except TimeoutError:
            return None


class InProcessBus:
    def __init__(self) -> None:
        self._subscribers: defaultdict[uuid.UUID, set[_QueueSubscription]] = defaultdict(set)

    async def publish(self, run_id: uuid.UUID, event: Event) -> None:
        for subscriber in self._subscribers.get(run_id, ()):
            subscriber.queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self, run_id: uuid.UUID) -> AsyncIterator[Subscription]:
        subscription = _QueueSubscription()
        self._subscribers[run_id].add(subscription)
        try:
            yield subscription
        finally:
            self._subscribers[run_id].discard(subscription)
            if not self._subscribers[run_id]:
                del self._subscribers[run_id]

    async def aclose(self) -> None:
        self._subscribers.clear()


def channel(run_id: uuid.UUID) -> str:
    return f"agentprobe:run:{run_id}"


class _PubSubSubscription:
    def __init__(self, pubsub: Any) -> None:
        self._pubsub = pubsub

    async def next(self, wait_s: float) -> Event | None:
        deadline = time.monotonic() + wait_s
        while (remaining := deadline - time.monotonic()) > 0:
            message = await self._pubsub.get_message(
                ignore_subscribe_messages=True, timeout=remaining
            )
            if message is not None and message["type"] == "message":
                event: Event = json.loads(message["data"])
                return event
        return None


class RedisBus:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish(self, run_id: uuid.UUID, event: Event) -> None:
        await self._redis.publish(channel(run_id), json.dumps(event))

    @asynccontextmanager
    async def subscribe(self, run_id: uuid.UUID) -> AsyncIterator[Subscription]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel(run_id))
        try:
            yield _PubSubSubscription(pubsub)
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    async def aclose(self) -> None:
        await self._redis.aclose()
