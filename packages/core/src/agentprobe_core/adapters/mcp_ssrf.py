"""The SSRF guard (`ssrf.py`, ADR 0012) ported to httpcore2/httpx2, the stack the MCP SDK's
Streamable HTTP client uses (`mcp` depends on `httpx2`, not `httpx`). The address
classification and policy (`classify`, `TargetPolicy`) are shared as-is; only the thin
network-backend wrapper differs, because it must subclass httpcore2's own base class and
raise httpcore2's own exceptions.
"""

from collections.abc import Iterable
from typing import Any

import anyio
import httpcore2
import httpx2

from agentprobe_core.adapters.ssrf import (
    Resolver,
    TargetBlocked,
    TargetPolicy,
    resolve_target,
    system_resolver,
)


class GuardedBackend2(httpcore2.AsyncNetworkBackend):
    """`ssrf.GuardedBackend`, for httpcore2's connection pool."""

    def __init__(
        self,
        *,
        policy: TargetPolicy,
        agent_allows_private: bool,
        resolver: Resolver = system_resolver,
        inner: httpcore2.AsyncNetworkBackend | None = None,
    ) -> None:
        self._policy = policy
        self._agent_allows_private = agent_allows_private
        self._resolver = resolver
        self._inner = inner or httpcore2.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 (httpcore2's backend interface)
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        try:
            with anyio.fail_after(timeout):
                addresses = await resolve_target(
                    host,
                    port,
                    policy=self._policy,
                    agent_allows_private=self._agent_allows_private,
                    resolver=self._resolver,
                    connect_error=httpcore2.ConnectError,
                )
        except TimeoutError as exc:
            raise httpcore2.ConnectTimeout(f"resolving {host} timed out") from exc
        # ponytail: addresses are tried in order, not raced (Happy Eyeballs), matching ssrf.py.
        error: Exception = httpcore2.ConnectError(f"could not connect to {host}")
        for address in addresses:
            try:
                return await self._inner.connect_tcp(
                    address, port, timeout, local_address, socket_options
                )
            except (httpcore2.ConnectError, httpcore2.ConnectTimeout) as exc:
                error = exc
        raise error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 (httpcore2's backend interface)
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        raise TargetBlocked("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def guarded_httpx2_client(
    *,
    policy: TargetPolicy,
    agent_allows_private: bool,
    timeout_s: float,
    resolver: Resolver = system_resolver,
) -> httpx2.AsyncClient:
    """An `httpx2.AsyncClient` whose every connection (including redirects) goes through the
    SSRF guard, the same way `HttpAdapter` builds its `httpx.AsyncClient` (ADR 0012).
    """
    ssl_context = httpx2.create_ssl_context()
    transport = httpx2.AsyncHTTPTransport(verify=ssl_context, trust_env=False)
    # httpx2 has no network_backend option, so swap in a pool whose every connection goes
    # through the guard, exactly as HttpAdapter does for httpx/httpcore.
    transport._pool = httpcore2.AsyncConnectionPool(
        ssl_context=ssl_context,
        network_backend=GuardedBackend2(
            policy=policy, agent_allows_private=agent_allows_private, resolver=resolver
        ),
    )
    return httpx2.AsyncClient(transport=transport, trust_env=False, timeout=timeout_s)
