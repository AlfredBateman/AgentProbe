"""Waking a sleeping agent host before a run or connection test (ADR 0036). Offline."""

import time

import httpx
import pytest

from agentprobe_api import wake
from agentprobe_api.wake import wake_target
from apitest import make_settings

DEMO = "https://agentprobe-demo-agents.onrender.com/support/v1/chat"


def fake_host(*outcomes: int | type[Exception]) -> tuple[httpx.AsyncClient, list[str]]:
    """A client whose host answers each request with the next outcome, the last one forever."""
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url}")
        outcome = outcomes[min(len(calls), len(outcomes)) - 1]
        if isinstance(outcome, int):
            return httpx.Response(outcome)
        raise outcome("asleep", request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handle)), calls


@pytest.fixture(autouse=True)
def no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wake, "RETRY_S", 0.001)


async def test_a_listed_host_is_polled_on_health_until_it_answers() -> None:
    client, calls = fake_host(httpx.ConnectError, 502, httpx.ReadTimeout, 200)
    settings = make_settings(wake_target_hosts=" Agentprobe-Demo-Agents.onrender.com ,other")
    await wake_target({"url": DEMO}, settings, client=client)
    assert calls == ["GET https://agentprobe-demo-agents.onrender.com/health"] * 4


async def test_any_answer_below_500_means_awake() -> None:
    client, calls = fake_host(404)
    settings = make_settings(wake_target_hosts="agentprobe-demo-agents.onrender.com")
    await wake_target({"url": DEMO}, settings, client=client)
    assert len(calls) == 1


@pytest.mark.parametrize("hosts", ["", "example.com", "demo-agents.onrender.com"])
async def test_other_hosts_are_never_called(hosts: str) -> None:
    client, calls = fake_host(200)
    await wake_target({"url": DEMO}, make_settings(wake_target_hosts=hosts), client=client)
    await wake_target({}, make_settings(wake_target_hosts=hosts), client=client)
    assert calls == []


async def test_a_host_that_never_wakes_gives_up_without_raising() -> None:
    client, calls = fake_host(503)
    settings = make_settings(wake_target_hosts="agentprobe-demo-agents.onrender.com")
    started = time.monotonic()
    await wake_target({"url": DEMO}, settings, budget_s=0.05, client=client)
    assert time.monotonic() - started < 1
    assert len(calls) >= 1  # the real call that follows reports the failure


async def test_the_wake_call_goes_through_the_ssrf_guard(caplog: pytest.LogCaptureFixture) -> None:
    # Listing a host doesn't exempt it: a metadata address is refused by the guard before any
    # connection, and the wake gives up at once (the agent call that follows reports it).
    settings = make_settings(wake_target_hosts="169.254.169.254")
    started = time.monotonic()
    await wake_target({"url": "http://169.254.169.254/latest/meta-data"}, settings)
    assert time.monotonic() - started < 1
    assert "ssrf guard blocked 169.254.169.254" in caplog.text
