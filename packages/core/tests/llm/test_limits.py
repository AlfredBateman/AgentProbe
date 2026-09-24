import random
from pathlib import Path
from typing import Any

import pytest

from agentprobe_core.llm.limits import DailyQuota, RateLimiter, with_backoff
from agentprobe_core.llm.types import LLMError, QuotaExhausted, TransientLLMError


def limiter(
    clock: Any, *, rpm: int = 100, rpd: int = 1000, path: Path | None = None
) -> RateLimiter:
    return RateLimiter(rpm=rpm, rpd=rpd, quota=DailyQuota(path, clock), clock=clock)


async def test_rpm_waits_for_the_window_to_slide(clock: Any) -> None:
    rl = limiter(clock, rpm=3)
    for _ in range(3):
        await rl.acquire("m")
    assert clock.sleeps == []
    await rl.acquire("m")  # fourth in the same minute waits for the first to age out
    assert clock.sleeps == [60.0]
    await rl.acquire("m")  # the old three are gone; one used in the new window
    assert clock.sleeps == [60.0]


async def test_rpm_is_per_model(clock: Any) -> None:
    rl = limiter(clock, rpm=1)
    await rl.acquire("a")
    await rl.acquire("b")
    assert clock.sleeps == []


async def test_rpd_fails_clearly_instead_of_waiting(clock: Any) -> None:
    rl = limiter(clock, rpd=2)
    await rl.acquire("m")
    await rl.acquire("m")
    with pytest.raises(QuotaExhausted, match=r"2/2 requests used today \(LLM_RPD\).*resets at"):
        await rl.acquire("m")
    await rl.acquire("other")  # other models keep their own daily quota


async def test_rpd_resets_at_pacific_midnight(clock: Any) -> None:
    rl = limiter(clock, rpd=1)
    await rl.acquire("m")
    with pytest.raises(QuotaExhausted):
        await rl.acquire("m")
    clock.advance(18 * 3600)  # 06:00 UTC next day = 23:00 PDT: still the same Pacific day
    with pytest.raises(QuotaExhausted):
        await rl.acquire("m")
    clock.advance(2 * 3600)  # 01:00 PDT on the 25th
    await rl.acquire("m")


async def test_rpd_persists_across_processes(clock: Any, tmp_path: Path) -> None:
    path = tmp_path / "quota.json"
    first = limiter(clock, rpd=2, path=path)
    await first.acquire("m")
    await first.acquire("m")
    second = limiter(clock, rpd=2, path=path)  # a new CLI run on the same day
    with pytest.raises(QuotaExhausted):
        await second.acquire("m")


def test_daily_usd_cap(clock: Any) -> None:
    from agentprobe_core.llm.types import BudgetExceeded

    quota = DailyQuota(None, clock)
    quota.check_usd(1.0)
    quota.add_usd(0.6)
    quota.add_usd(0.5)
    with pytest.raises(BudgetExceeded, match="LLM_BUDGET_USD_PER_DAY"):
        quota.check_usd(1.0)


class Flaky:
    def __init__(self, failures: list[Exception]) -> None:
        self.failures = failures
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return "ok"


def transient(retry_after: float | None = None) -> TransientLLMError:
    return TransientLLMError("429", status=429, retry_after=retry_after)


async def test_backoff_retries_with_bounded_full_jitter(clock: Any) -> None:
    fn = Flaky([transient(), transient(), transient()])
    result = await with_backoff(
        fn, max_retries=4, clock=clock, rng=random.Random(7), base_s=1.0, cap_s=60.0
    )
    assert result == "ok" and fn.calls == 4
    assert len(clock.sleeps) == 3
    for n, delay in enumerate(clock.sleeps):
        assert 0 <= delay <= 2**n  # full jitter: uniform(0, base * 2^n)


async def test_backoff_is_deterministic_for_a_seed(clock: Any) -> None:
    await with_backoff(Flaky([transient()] * 3), max_retries=3, clock=clock, rng=random.Random(1))
    first = list(clock.sleeps)
    clock.sleeps.clear()
    await with_backoff(Flaky([transient()] * 3), max_retries=3, clock=clock, rng=random.Random(1))
    assert clock.sleeps == first


async def test_backoff_honors_retry_after(clock: Any) -> None:
    fn = Flaky([transient(retry_after=30.0)])
    await with_backoff(fn, max_retries=2, clock=clock, rng=random.Random(0))
    assert clock.sleeps == [30.0]


async def test_backoff_caps_exponential_growth(clock: Any) -> None:
    fn = Flaky([transient()] * 10)
    await with_backoff(fn, max_retries=10, clock=clock, rng=random.Random(3), cap_s=5.0)
    assert max(clock.sleeps) <= 5.0


async def test_backoff_gives_up_after_max_retries(clock: Any) -> None:
    fn = Flaky([transient()] * 5)
    with pytest.raises(TransientLLMError):
        await with_backoff(fn, max_retries=2, clock=clock, rng=random.Random(0))
    assert fn.calls == 3


async def test_backoff_fails_fast_on_a_very_long_retry_after(clock: Any) -> None:
    fn = Flaky([transient(retry_after=3600.0)])
    with pytest.raises(TransientLLMError):
        await with_backoff(fn, max_retries=5, clock=clock, rng=random.Random(0))
    assert clock.sleeps == []


async def test_backoff_does_not_retry_permanent_errors(clock: Any) -> None:
    fn = Flaky([LLMError("bad request")])
    with pytest.raises(LLMError, match="bad request"):
        await with_backoff(fn, max_retries=5, clock=clock, rng=random.Random(0))
    assert fn.calls == 1
