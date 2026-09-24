from datetime import UTC, datetime, timedelta

import pytest


class FakeClock:
    """Time only moves when something sleeps (or a test calls advance)."""

    def __init__(self, start: datetime) -> None:
        self.t = 0.0
        self.start = start
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def now(self) -> datetime:
        return self.start + timedelta(seconds=self.t)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock() -> FakeClock:
    # 12:00 UTC = 05:00 in Los Angeles (PDT), so the Pacific day is 2026-09-24.
    return FakeClock(datetime(2026, 9, 24, 12, 0, tzinfo=UTC))
