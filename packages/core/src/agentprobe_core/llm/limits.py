"""Rate limits, daily quota, per-run budget and retry backoff. Time comes from a `Clock` so
tests drive it with a fake one instead of sleeping.
"""

import asyncio
import json
import os
import random
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from agentprobe_core.llm.types import BudgetExceeded, QuotaExhausted, TransientLLMError, Usage

# Gemini's daily quotas reset at midnight Pacific time.
QUOTA_TZ = ZoneInfo("America/Los_Angeles")
# A Retry-After longer than this means "come back later", not "retry": fail instead of hanging.
MAX_RETRY_AFTER_S = 300.0


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def now(self) -> datetime: ...
    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def now(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class DailyQuota:
    """Requests per model and estimated USD for the current Pacific-time day.

    With a path, the counts persist so the daily cap holds across processes (every CLI run
    is a new process). Without one, they live in memory.
    """

    def __init__(self, path: Path | None, clock: Clock) -> None:
        self._path = path
        self._clock = clock
        self._state: dict[str, Any] = {}

    def _today(self) -> str:
        return self._clock.now().astimezone(QUOTA_TZ).date().isoformat()

    def _load(self) -> dict[str, Any]:
        today = self._today()
        state = self._state
        if self._path is not None:
            try:
                state = json.loads(self._path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                state = {}
        if state.get("date") != today:
            state = {"date": today, "requests": {}, "usd": 0.0}
        return state

    def _save(self, state: dict[str, Any]) -> None:
        self._state = state
        if self._path is None:
            return
        # ponytail: read-modify-write without a cross-process lock, so two concurrent processes
        # can undercount by a few requests. Move the counter to Redis/Postgres for multi-worker.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, self._path)

    def _reset_at(self) -> str:
        now = self._clock.now().astimezone(QUOTA_TZ)
        midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), QUOTA_TZ)
        return midnight.isoformat()

    def reserve_request(self, model: str, rpd: int) -> None:
        state = self._load()
        used = int(state["requests"].get(model, 0))
        if used >= rpd:
            raise QuotaExhausted(
                f"{model}: {used}/{rpd} requests used today (LLM_RPD); "
                f"the quota resets at {self._reset_at()}"
            )
        state["requests"][model] = used + 1
        self._save(state)

    def requests(self, model: str) -> int:
        return int(self._load()["requests"].get(model, 0))

    def check_usd(self, max_usd_per_day: float) -> None:
        spent = float(self._load()["usd"])
        if spent >= max_usd_per_day:
            raise BudgetExceeded(
                f"daily LLM budget used up: ${spent:.4f} of ${max_usd_per_day:.2f} "
                f"(LLM_BUDGET_USD_PER_DAY); resets at {self._reset_at()}"
            )

    def add_usd(self, usd: float) -> None:
        if usd:
            state = self._load()
            state["usd"] = float(state["usd"]) + usd
            self._save(state)


class RateLimiter:
    """Per-model requests per minute (sliding window, waits) and per day (DailyQuota, fails)."""

    def __init__(self, *, rpm: int, rpd: int, quota: DailyQuota, clock: Clock) -> None:
        self._rpm = rpm
        self._rpd = rpd
        self._quota = quota
        self._clock = clock
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def acquire(self, model: str) -> None:
        async with self._locks[model]:
            window = self._windows[model]
            while True:
                now = self._clock.monotonic()
                while window and now - window[0] >= 60.0:
                    window.popleft()
                if len(window) < self._rpm:
                    break
                await self._clock.sleep(60.0 - (now - window[0]))
            # After the wait, so a request that is still waiting doesn't hold a daily slot.
            self._quota.reserve_request(model, self._rpd)
            window.append(self._clock.monotonic())


class BudgetGuard:
    """Per-run caps. A call is reserved before it's sent, so the cap is never overshot on
    calls; tokens and USD are only known afterwards, so the call that crosses those caps
    completes and the next one is refused.
    """

    def __init__(self, *, max_calls: int, max_tokens: int, max_usd: float) -> None:
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.max_usd = max_usd
        self.calls = 0
        self.tokens = 0
        self.usd = 0.0

    def reserve_call(self) -> None:
        if self.calls >= self.max_calls:
            raise BudgetExceeded(
                f"run budget used up: {self.calls}/{self.max_calls} LLM calls "
                "(LLM_BUDGET_MAX_CALLS_PER_RUN)"
            )
        if self.tokens >= self.max_tokens:
            raise BudgetExceeded(
                f"run budget used up: {self.tokens}/{self.max_tokens} tokens "
                "(LLM_BUDGET_MAX_TOKENS_PER_RUN)"
            )
        if self.usd >= self.max_usd:
            raise BudgetExceeded(
                f"run budget used up: ${self.usd:.4f} of ${self.max_usd:.2f} "
                "(LLM_BUDGET_USD_PER_RUN)"
            )
        self.calls += 1

    def record(self, usage: Usage) -> None:
        self.tokens += usage.total_tokens
        self.usd += usage.cost_usd


async def with_backoff[T](
    attempt: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
    clock: Clock,
    rng: random.Random,
    base_s: float = 1.0,
    cap_s: float = 60.0,
    retry_on: type[Exception] = TransientLLMError,
) -> T:
    """Retries `retry_on` with full-jitter exponential backoff, waiting at least as long as
    the exception's `retry_after` (the provider's Retry-After), if it has one.
    """
    for n in range(max_retries + 1):
        try:
            return await attempt()
        except retry_on as exc:
            retry_after: float | None = getattr(exc, "retry_after", None)
            if n == max_retries:
                raise
            if retry_after is not None and retry_after > MAX_RETRY_AFTER_S:
                raise
            delay = rng.uniform(0, min(cap_s, base_s * 2**n))
            if retry_after is not None:
                delay = max(delay, retry_after)
            await clock.sleep(delay)
    raise AssertionError("unreachable")
