"""MCP adapter: connects over stdio or Streamable HTTP, lists
tools, and calls one per case's `call: {tool, arguments}` (ADR 0010) instead of chat-style
`input`. Every call becomes a `ToolCallStep` + `ToolResultStep` trace pair (ADR 0012's shared
step model), so `tool_called` / `tool_not_called` / `tool_args_match` judges work unchanged,
and `contains`/`regex`/etc. run on the tool's result the same way they run on chat output.

Server side: `adapter_type=mcp` agents are Streamable HTTP only (`McpHttpConfig`). stdio
(`McpStdioConfig`) means launching an arbitrary local command, so — like the Python adapter —
it's CLI-only: refused by `build_adapter` and, as a backstop, by this module in any process
that has imported `agentprobe_api`. HTTP transport goes through the same SSRF guard as the
HTTP adapter, ported to httpcore2/httpx2 (`mcp_ssrf.py`) because the MCP SDK's Streamable HTTP
client is built on httpx2, not httpx.

Each call opens and closes its own MCP session (`_build_client()` fresh, `async with` it, one
`call_tool`). `run_suite` runs attempts from worker tasks under a `TaskGroup`, and anyio's
cancel scopes are task-affine: a session entered lazily in one worker task but closed by
`aclose()` from the CLI's or the caller's own task (a different one) raises "attempted to exit
cancel scope in a different task than it was entered in" — reproducible through both a
persistent shared session and a "reconnect after failure" attempt at one. Opening and closing
within the same call sidesteps it, at the cost of paying the MCP handshake per call rather
than reusing one session across a run; the shared `httpx2.AsyncClient` (HTTP transport) still
pools connections underneath, so it costs a round trip per attempt, not a new TCP connection.
"""

import asyncio
import json
import random
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Literal

import httpcore2
import httpx2
from mcp import Client, MCPError, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue, field_validator

from agentprobe_core.adapters.http import check_header
from agentprobe_core.adapters.mcp_ssrf import guarded_httpx2_client
from agentprobe_core.adapters.ssrf import TargetBlocked, TargetPolicy
from agentprobe_core.adapters.types import (
    AdapterNotAllowed,
    AgentResponse,
    McpCall,
    ToolCallStep,
    ToolResultStep,
    TraceStep,
)
from agentprobe_core.llm.limits import Clock, SystemClock, with_backoff

SERVER_PACKAGE = "agentprobe_api"  # mirrors adapters/python.py's CLI-only guard


class McpHttpConfig(BaseModel):
    """An MCP agent's stored config over Streamable HTTP — the only transport the server
    runs; stdio is CLI-only (`McpStdioConfig`).
    """

    model_config = ConfigDict(extra="forbid")

    transport: Literal["http"] = "http"
    url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict, max_length=50)
    timeout_ms: int = Field(default=30_000, gt=0, le=120_000)
    max_retries: int = Field(default=2, ge=0, le=5)
    # The agent's half of the private-target opt-in; the server's half is TargetPolicy.
    allow_private: bool = False

    @field_validator("headers")
    @classmethod
    def _plain_headers(cls, headers: dict[str, str]) -> dict[str, str]:
        for name, value in headers.items():
            check_header(name, value, secret=False)
        return headers


class McpStdioConfig(BaseModel):
    """CLI-only: launches `command` as a local subprocess and speaks MCP over its stdio."""

    model_config = ConfigDict(extra="forbid")

    transport: Literal["stdio"] = "stdio"
    command: str = Field(min_length=1, max_length=500)
    args: list[str] = Field(default_factory=list, max_length=50)
    env: dict[str, str] = Field(default_factory=dict, max_length=50)
    timeout_ms: int = Field(default=30_000, gt=0, le=120_000)
    max_retries: int = Field(default=2, ge=0, le=5)


McpAdapterConfig = Annotated[McpHttpConfig | McpStdioConfig, Field(discriminator="transport")]


class _CallFailed(Exception):
    """An attempt failed; `_call` turns the last one into an error response."""


class _Transient(_CallFailed):
    """Worth retrying: the call never reached the server (mirrors http.py's `_Transient`)."""


def _unwrap(exc: BaseException) -> BaseException:
    """anyio's `TaskGroup` wraps a connection failure in a single-member `ExceptionGroup`;
    this walks down to the real cause.
    """
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


def _classify(exc: BaseException) -> Exception:
    leaf = _unwrap(exc)
    if isinstance(leaf, TargetBlocked):
        return _CallFailed(str(leaf))
    if isinstance(leaf, MCPError):
        return _CallFailed(f"MCP protocol error {leaf.code}: {leaf.message}")
    if isinstance(
        leaf,
        httpx2.ConnectError
        | httpx2.ConnectTimeout
        | httpx2.PoolTimeout
        | httpcore2.ConnectError
        | httpcore2.ConnectTimeout,
    ):
        return _Transient(f"could not connect: {leaf}")
    if isinstance(leaf, Exception):
        return _CallFailed(f"{type(leaf).__name__}: {leaf}")
    return _CallFailed(str(leaf))  # pragma: no cover (a BaseException that isn't an Exception)


def _output(result: CallToolResult) -> str:
    if result.structured_content is not None:
        return json.dumps(result.structured_content)
    return "\n".join(block.text for block in result.content if isinstance(block, TextContent))


class McpAdapter:
    def __init__(
        self,
        config: McpHttpConfig | McpStdioConfig,
        *,
        policy: TargetPolicy | None = None,
        clock: Clock | None = None,
    ) -> None:
        if isinstance(config, McpStdioConfig) and SERVER_PACKAGE in sys.modules:
            raise AdapterNotAllowed(
                "MCP stdio transport is CLI-only; the server can't launch subprocesses"
            )
        self._config = config
        self._clock = clock or SystemClock()
        self._rng = random.Random()  # noqa: S311 (jitter, not crypto)
        self._http_client: httpx2.AsyncClient | None = None
        if isinstance(config, McpHttpConfig):
            self._http_client = guarded_httpx2_client(
                policy=policy or TargetPolicy.from_env(),
                agent_allows_private=config.allow_private,
                timeout_s=config.timeout_ms / 1000,
            )
            if config.headers:
                self._http_client.headers.update(config.headers)

    def _build_client(self) -> Client:
        config = self._config
        if isinstance(config, McpHttpConfig):
            transport = streamable_http_client(str(config.url), http_client=self._http_client)
            return Client(transport)
        params = StdioServerParameters(
            command=config.command, args=config.args, env=config.env or None
        )
        return Client(params)

    async def __aenter__(self) -> "McpAdapter":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        # Only the shared HTTP client persists across calls (pooling connections); it has no
        # anyio task affinity, so closing it from whatever task calls aclose() is safe.
        if self._http_client is not None:
            await self._http_client.aclose()

    async def invoke(
        self, input: str, context: Sequence[JsonValue] = (), *, call: McpCall | None = None
    ) -> AgentResponse:
        if call is None:
            return AgentResponse(
                output="",
                steps=[],
                latency_ms=0.0,
                error="the MCP adapter needs a case with `call: {tool, arguments}`, not `input`",
            )
        return await self._call(call, max_retries=self._config.max_retries)

    async def test_connection(self) -> AgentResponse:
        """One `list_tools` call, no retries: `error` is None when the target passes the SSRF
        policy and the MCP handshake and tool listing succeed.
        """
        timeout_s = self._config.timeout_ms / 1000
        t0 = time.perf_counter()
        try:
            async with self._build_client() as client:
                async with asyncio.timeout(timeout_s):
                    await client.list_tools()
        except TimeoutError:
            error = f"no response within {timeout_s:g}s"
        except BaseException as exc:
            error = str(_classify(exc))
        else:
            return AgentResponse(output="", steps=[], latency_ms=(time.perf_counter() - t0) * 1000)
        return AgentResponse(
            output="", steps=[], latency_ms=(time.perf_counter() - t0) * 1000, error=error
        )

    async def _call(self, call: McpCall, *, max_retries: int) -> AgentResponse:
        timeout_s = self._config.timeout_ms / 1000
        latency_ms = 0.0
        started = datetime.now(UTC)

        async def attempt() -> AgentResponse:
            nonlocal latency_ms
            t0 = time.perf_counter()
            try:
                async with self._build_client() as client:
                    async with asyncio.timeout(timeout_s):
                        result = await client.call_tool(
                            call.tool, call.arguments, read_timeout_seconds=timeout_s
                        )
            except TimeoutError:
                latency_ms = (time.perf_counter() - t0) * 1000
                raise _CallFailed(f"no response within {timeout_s:g}s") from None
            except BaseException as exc:
                latency_ms = (time.perf_counter() - t0) * 1000
                raise _classify(exc) from exc
            latency_ms = (time.perf_counter() - t0) * 1000
            output = _output(result)
            steps: list[TraceStep] = [
                ToolCallStep(tool=call.tool, arguments=call.arguments, timestamp=started),
                ToolResultStep(
                    tool=call.tool,
                    result=result.structured_content
                    if result.structured_content is not None
                    else output,
                    timestamp=started,
                    duration_ms=latency_ms,
                ),
            ]
            return AgentResponse(
                output=output, steps=steps, latency_ms=latency_ms, tool_calls_reported=True
            )

        try:
            return await with_backoff(
                attempt,
                max_retries=max_retries,
                clock=self._clock,
                rng=self._rng,
                base_s=0.5,
                cap_s=8.0,
                retry_on=_Transient,
            )
        except _CallFailed as exc:
            return AgentResponse(
                output="",
                steps=[],
                latency_ms=latency_ms,
                error=str(exc),
                retryable=isinstance(exc, _Transient),
            )
