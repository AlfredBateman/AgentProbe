"""Offline checks for the public-deploy guards (ADR 0035, ADR 0036): the trusted client IP,
argon2's memory bound, startup refusals, readiness, and the caps that need no database.
"""

import asyncio
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from starlette.requests import Request

from agentprobe_api import limits
from agentprobe_api.auth import ARGON2_SLOTS, PROXY_SECRET_HEADER, _argon2, client_ip
from agentprobe_api.errors import ApiError
from agentprobe_api.main import check_production_settings, create_app
from apitest import make_settings

SECRET = "s" * 40
PEER = "10.214.3.4"  # Render's proxy, the connecting address
XFF = "x-forwarded-for"
# What the API sees through the web proxy: its browser entry, then Vercel's and Render's hops.
VIA_PROXY = "203.0.113.5, 76.76.21.21, 10.214.0.1"


def request(headers: list[tuple[str, str]] | dict[str, str], peer: str = PEER) -> Request:
    pairs = headers.items() if isinstance(headers, dict) else headers
    raw = [(k.lower().encode(), v.encode()) for k, v in pairs]
    return Request({"type": "http", "headers": raw, "client": (peer, 1234)})


@pytest.mark.parametrize(
    ("configured", "headers", "expected"),
    [
        # Through the web proxy: the leftmost entry is the browser, the rest are hops.
        (SECRET, {PROXY_SECRET_HEADER: SECRET, XFF: VIA_PROXY}, "203.0.113.5"),
        (SECRET, {PROXY_SECRET_HEADER: SECRET, XFF: "2001:db8::1, 10.214.0.1"}, "2001:db8::1"),
        (SECRET, {PROXY_SECRET_HEADER: SECRET, XFF: " 203.0.113.5 "}, "203.0.113.5"),
        # Spoofed without the secret: a caller's X-Forwarded-For is ignored, whatever it says.
        (SECRET, {XFF: "203.0.113.5"}, PEER),
        (SECRET, {XFF: VIA_PROXY}, PEER),
        (SECRET, {PROXY_SECRET_HEADER: "guess", XFF: "203.0.113.5"}, PEER),
        (SECRET, {PROXY_SECRET_HEADER: SECRET[:-1], XFF: "203.0.113.5"}, PEER),  # a prefix
        (SECRET, {PROXY_SECRET_HEADER: SECRET + "s", XFF: "203.0.113.5"}, PEER),
        (SECRET, {PROXY_SECRET_HEADER: "", XFF: "203.0.113.5"}, PEER),
        # No secret configured (local, compose, e2e): never trusted, not even an empty match.
        (None, {PROXY_SECRET_HEADER: "", XFF: "203.0.113.5"}, PEER),
        (None, {PROXY_SECRET_HEADER: SECRET, XFF: "203.0.113.5"}, PEER),
        # The right secret but nothing usable: the proxy's address, never the header text.
        (SECRET, {PROXY_SECRET_HEADER: SECRET, XFF: "evil, 1.2.3.4"}, PEER),
        (SECRET, {PROXY_SECRET_HEADER: SECRET, XFF: ""}, PEER),
        (SECRET, {PROXY_SECRET_HEADER: SECRET}, PEER),
        # The retired x-agentprobe-client-ip header means nothing now, secret or not.
        (
            SECRET,
            {PROXY_SECRET_HEADER: SECRET, "x-agentprobe-client-ip": "1.2.3.4", XFF: VIA_PROXY},
            "203.0.113.5",
        ),
        (SECRET, {PROXY_SECRET_HEADER: SECRET, "x-agentprobe-client-ip": "1.2.3.4"}, PEER),
        # Platform client-IP headers aren't trusted either: only the secret proves a hop.
        (SECRET, {"true-client-ip": "1.2.3.4", "cf-connecting-ip": "1.2.3.4"}, PEER),
    ],
)
def test_client_ip_trusts_x_forwarded_for_only_with_the_proxy_secret(
    configured: str | None, headers: dict[str, str], expected: str
) -> None:
    settings = make_settings(proxy_secret=SecretStr(configured) if configured else None)
    assert client_ip(request(headers), settings) == expected


def test_a_second_x_forwarded_for_header_line_cannot_take_the_lead() -> None:
    # Only the first line is read: a hop that adds its own line after the web proxy's,
    # instead of appending to it, doesn't change which entry is the browser.
    headers = [(PROXY_SECRET_HEADER, SECRET), (XFF, "203.0.113.5"), (XFF, "1.2.3.4")]
    assert client_ip(request(headers), make_settings(proxy_secret=SecretStr(SECRET))) == (
        "203.0.113.5"
    )


async def test_argon2_runs_at_most_two_at_a_time() -> None:
    app = create_app(make_settings())
    fake = SimpleNamespace(app=app)
    lock = threading.Lock()
    active, peak = 0, 0

    def slow_hash(_: str) -> str:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return "hash"

    results = await asyncio.gather(*(_argon2(fake, slow_hash, "pw") for _ in range(8)))  # type: ignore[arg-type]
    assert results == ["hash"] * 8
    assert peak == ARGON2_SLOTS == 2


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"web_origin": "https://agentprobe.example", "cookie_secure": False}, "COOKIE_SECURE"),
        ({"proxy_secret": SecretStr("short")}, "PROXY_SECRET"),
    ],
)
def test_unsafe_production_settings_refuse_to_start(
    overrides: dict[str, object], error: str
) -> None:
    with pytest.raises(RuntimeError, match=error):
        check_production_settings(make_settings(**overrides))


def test_safe_settings_start() -> None:
    check_production_settings(
        make_settings(web_origin="https://agentprobe.example", proxy_secret=SecretStr(SECRET))
    )
    check_production_settings(
        make_settings(web_origin="http://localhost:3000", cookie_secure=False)
    )


class FakeSession:
    def __init__(self, fail: bool) -> None:
        self.fail = fail

    async def execute(self, _statement: object) -> None:
        if self.fail:
            raise OSError("connection refused")


@pytest.mark.parametrize(
    ("fail", "status", "body"),
    [
        (False, 200, {"status": "ready", "commit": "abc123"}),
        (True, 503, {"status": "unavailable"}),
    ],
)
async def test_ready_reports_whether_the_database_answers_and_the_commit(
    fail: bool, status: int, body: dict[str, str]
) -> None:
    app = create_app(make_settings(render_git_commit="abc123"))

    @asynccontextmanager
    async def sessions() -> AsyncIterator[FakeSession]:
        yield FakeSession(fail)

    app.state.sessionmaker = sessions
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        r = await client.get("/ready")
    assert (r.status_code, r.json()) == (status, body)


def test_case_cap() -> None:
    limits.check_cases(make_settings(), 500)  # unset: unlimited
    limits.check_cases(make_settings(max_cases_per_suite=3), 3)
    with pytest.raises(ApiError) as exc:
        limits.check_cases(make_settings(max_cases_per_suite=3), 4)
    assert exc.value.status == 422


async def test_live_budget_is_not_consulted_for_mock_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    # None of these reach the database: `db` would raise if touched.
    monkeypatch.setenv("LLM_PROVIDER", "litellm")
    settings = make_settings(llm_global_usd_per_day=0.0)
    await limits.check_live_budget(None, settings, mock=True)  # type: ignore[arg-type]
    await limits.check_live_budget(None, make_settings(), mock=False)  # type: ignore[arg-type]
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    await limits.check_live_budget(None, settings, mock=False)  # type: ignore[arg-type]
