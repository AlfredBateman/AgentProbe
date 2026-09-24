"""Test helpers: fakes for the socket layer *under* the SSRF guard, so tests see exactly
where the guard connects, which hostname TLS gets, and what bytes go out, without a network.
"""

import json
import ssl
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpcore

from agentprobe_core.adapters import HttpAdapter
from agentprobe_core.adapters.ssrf import Resolver

PUBLIC_IP = "93.184.216.34"
OTHER_PUBLIC_IP = "151.101.1.69"
HOST = "agent.example.com"


def http_response(
    status: int = 200, body: Any = None, headers: tuple[str, ...] = (), raw: bytes | None = None
) -> bytes:
    payload = raw if raw is not None else json.dumps(body or {"output": "ok"}).encode()
    head = [f"HTTP/1.1 {status} X", f"Content-Length: {len(payload)}", "Connection: close"]
    return ("\r\n".join([*head, *headers]) + "\r\n\r\n").encode() + payload


class FakeStream(httpcore.AsyncMockStream):
    def __init__(self, response: bytes, backend: "FakeBackend") -> None:
        super().__init__([response])
        self._backend = backend

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:  # noqa: ASYNC109
        self._backend.sent += buffer

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,  # noqa: ASYNC109 (httpcore's interface)
    ) -> httpcore.AsyncNetworkStream:
        self._backend.tls.append((server_hostname, ssl_context))
        return self


class FakeBackend(httpcore.AsyncNetworkBackend):
    """Serves one scripted response per connection. A response may be an exception to raise
    at connect time instead."""

    def __init__(self, *responses: bytes | Exception) -> None:
        self.responses = list(responses)
        self.connects: list[tuple[str, int]] = []
        self.tls: list[tuple[str | None, ssl.SSLContext]] = []
        self.sent = b""

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 (httpcore's interface)
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connects.append((host, port))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeStream(response, self)

    async def sleep(self, seconds: float) -> None:
        pass


def static_resolver(answers: dict[str, list[str]], calls: list[str] | None = None) -> Resolver:
    async def resolve(host: str, port: int) -> list[str]:
        if calls is not None:
            calls.append(host)
        if host not in answers:
            raise OSError(f"no such host {host}")
        return answers[host]

    return resolve


class FakeClock:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return sum(self.sleeps)

    def now(self) -> datetime:
        return datetime(2026, 9, 24, tzinfo=UTC)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


MakeAdapter = Callable[..., HttpAdapter]
