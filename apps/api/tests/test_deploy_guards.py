"""Offline checks for the public-deploy guards (ADR 0035): the trusted client IP, startup
refusals, readiness, and the caps that need no database.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from pydantic import SecretStr
from starlette.requests import Request

from agentprobe_api import limits
from agentprobe_api.auth import CLIENT_IP_HEADER, PROXY_SECRET_HEADER, client_ip
from agentprobe_api.errors import ApiError
from agentprobe_api.main import check_production_settings, create_app
from apitest import make_settings

SECRET = "s" * 40


def request(headers: dict[str, str], peer: str = "198.51.100.9") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 1234)})


@pytest.mark.parametrize(
    ("configured", "headers", "expected"),
    [
        # The web proxy's secret: its forwarded browser IP is the one limits key on.
        (SECRET, {PROXY_SECRET_HEADER: SECRET, CLIENT_IP_HEADER: "203.0.113.5"}, "203.0.113.5"),
        (SECRET, {PROXY_SECRET_HEADER: SECRET, CLIENT_IP_HEADER: "2001:db8::1"}, "2001:db8::1"),
        # A wrong or missing secret: the forwarded IP is ignored, whatever it says.
        (SECRET, {PROXY_SECRET_HEADER: "guess", CLIENT_IP_HEADER: "203.0.113.5"}, "198.51.100.9"),
        (SECRET, {CLIENT_IP_HEADER: "203.0.113.5"}, "198.51.100.9"),
        # No secret configured (local, compose, e2e): never trusted.
        (None, {PROXY_SECRET_HEADER: "", CLIENT_IP_HEADER: "203.0.113.5"}, "198.51.100.9"),
        # The right secret with a malformed IP falls back to the peer, not the header text.
        (SECRET, {PROXY_SECRET_HEADER: SECRET, CLIENT_IP_HEADER: "evil, 1.2.3.4"}, "198.51.100.9"),
    ],
)
def test_client_ip_trusts_the_forwarded_ip_only_with_the_proxy_secret(
    configured: str | None, headers: dict[str, str], expected: str
) -> None:
    settings = make_settings(proxy_secret=SecretStr(configured) if configured else None)
    assert client_ip(request(headers), settings) == expected


FLY = {"client_ip_header": "fly-client-ip", "forwarded_allow_ips": "172.16.0.0/12"}


@pytest.mark.parametrize(
    ("peer", "overrides", "headers", "expected"),
    [
        # Fly's proxy (a 172.16/12 peer) sets Fly-Client-IP: a direct caller's real address.
        ("172.19.3.4", FLY, {"fly-client-ip": "203.0.113.5"}, "203.0.113.5"),
        # From any other peer the header is just text a client sent.
        ("198.51.100.9", FLY, {"fly-client-ip": "203.0.113.5"}, "198.51.100.9"),
        # Not configured: ignored even from a trusted peer.
        (
            "172.19.3.4",
            {"forwarded_allow_ips": "172.16.0.0/12"},
            {"fly-client-ip": "1.2.3.4"},
            "172.19.3.4",
        ),
        # Missing or malformed: key on the proxy rather than on header text.
        ("172.19.3.4", FLY, {"fly-client-ip": "not an ip"}, "172.19.3.4"),
        ("172.19.3.4", FLY, {}, "172.19.3.4"),
        # The web proxy's secret wins over the platform header (the browser, not the web server).
        (
            "172.19.3.4",
            {**FLY, "proxy_secret": SecretStr(SECRET)},
            {
                PROXY_SECRET_HEADER: SECRET,
                CLIENT_IP_HEADER: "203.0.113.7",
                "fly-client-ip": "3.3.3.3",
            },
            "203.0.113.7",
        ),
        (
            "10.0.0.1",
            {**FLY, "forwarded_allow_ips": "*"},
            {"fly-client-ip": "203.0.113.5"},
            "203.0.113.5",
        ),
    ],
)
def test_client_ip_trusts_the_platform_header_only_from_its_proxy(
    peer: str, overrides: dict[str, object], headers: dict[str, str], expected: str
) -> None:
    assert client_ip(request(headers, peer), make_settings(**overrides)) == expected


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"web_origin": "https://agentprobe.example", "cookie_secure": False}, "COOKIE_SECURE"),
        ({"proxy_secret": SecretStr("short")}, "PROXY_SECRET"),
        ({"forwarded_allow_ips": "172.16.0.0/12, fly-proxy"}, "FORWARDED_ALLOW_IPS"),
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
    ("fail", "status", "body"), [(False, 200, "ready"), (True, 503, "unavailable")]
)
async def test_ready_reports_whether_the_database_answers(
    fail: bool, status: int, body: str
) -> None:
    app = create_app(make_settings())

    @asynccontextmanager
    async def sessions() -> AsyncIterator[FakeSession]:
        yield FakeSession(fail)

    app.state.sessionmaker = sessions
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        r = await client.get("/ready")
    assert (r.status_code, r.json()) == (status, {"status": body})


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
