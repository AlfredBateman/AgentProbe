"""The MCP adapter (ADR 0023) against a real local MCP server over loopback Streamable HTTP:
tool calls, the three error paths the SDK distinguishes (ToolError, MCPError, a crash),
argument-schema validation, retries/timeouts, the SSRF guard, and the stdio/CLI-only
restriction.
"""

import sys
import threading
import time
import types
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

import pytest
import uvicorn
from mcp import MCPError
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import TypeAdapter, ValidationError
from starlette.applications import Starlette
from starlette.routing import Mount

from adapterfakes import FakeClock
from agentprobe_core.adapters import build_adapter
from agentprobe_core.adapters.mcp import (
    SERVER_PACKAGE,
    McpAdapter,
    McpAdapterConfig,
    McpHttpConfig,
    McpStdioConfig,
)
from agentprobe_core.adapters.ssrf import TargetPolicy
from agentprobe_core.adapters.types import AdapterNotAllowed, McpCall, ToolCallStep, ToolResultStep


def _build_test_server() -> MCPServer:
    mcp = MCPServer("Test Tools")

    @mcp.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @mcp.tool()
    def fail_tool_error(x: str) -> str:
        raise ToolError(f"bad input: {x}")

    @mcp.tool()
    def fail_mcp_error(x: str) -> str:
        raise MCPError(code=-32602, message=f"rejected: {x}")

    @mcp.tool()
    def fail_crash(x: str) -> str:
        raise KeyError("internal-detail-never-leaked")

    return mcp


@contextmanager
def _serve(mcp: MCPServer) -> Iterator[str]:
    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = Starlette(routes=[Mount("/tools", app=mcp.streamable_http_app())], lifespan=lifespan)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("the test MCP server did not start")
        time.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}/tools/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=15)


@pytest.fixture(scope="module")
def server_url() -> Iterator[str]:
    with _serve(_build_test_server()) as url:
        yield url


@pytest.fixture(autouse=True)
def not_in_server(monkeypatch: pytest.MonkeyPatch) -> None:
    # Other tests in this pytest process import the API; this module is about the CLI/core.
    monkeypatch.delitem(sys.modules, SERVER_PACKAGE, raising=False)


def adapter(url: str, **overrides: object) -> McpAdapter:
    config = McpHttpConfig.model_validate({"url": url, "allow_private": True, **overrides})
    return McpAdapter(config, policy=TargetPolicy(allow_private=True))


# --- config validation -----------------------------------------------------------------


def test_http_config_needs_a_url() -> None:
    with pytest.raises(ValidationError):
        McpHttpConfig.model_validate({})


def test_stdio_config_needs_a_command() -> None:
    with pytest.raises(ValidationError):
        McpStdioConfig.model_validate({"transport": "stdio"})


def test_the_union_discriminates_on_transport() -> None:
    adapter_type = TypeAdapter(McpAdapterConfig)
    http = adapter_type.validate_python({"transport": "http", "url": "https://x.test/mcp"})
    stdio = adapter_type.validate_python({"transport": "stdio", "command": "run-server"})
    assert isinstance(http, McpHttpConfig)
    assert isinstance(stdio, McpStdioConfig)
    with pytest.raises(ValidationError):
        adapter_type.validate_python({"transport": "carrier-pigeon"})


def test_http_config_rejects_bad_headers() -> None:
    with pytest.raises(ValidationError, match="Authorization"):
        McpHttpConfig.model_validate(
            {"url": "https://x.test/mcp", "headers": {"Authorization": "Bearer t"}}
        )


# --- build_adapter: server-side restriction ---------------------------------------------


def test_build_adapter_accepts_http() -> None:
    built = build_adapter("mcp", {"transport": "http", "url": "https://x.test/mcp"})
    assert isinstance(built, McpAdapter)


def test_build_adapter_refuses_stdio() -> None:
    with pytest.raises(AdapterNotAllowed, match="CLI-only"):
        build_adapter("mcp", {"transport": "stdio", "command": "evil"})


def test_mcp_adapter_refuses_stdio_in_a_server_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, SERVER_PACKAGE, types.ModuleType(SERVER_PACKAGE))
    with pytest.raises(AdapterNotAllowed, match="CLI-only"):
        McpAdapter(McpStdioConfig.model_validate({"command": "evil"}))


def test_mcp_adapter_allows_stdio_outside_a_server_process() -> None:
    McpAdapter(McpStdioConfig.model_validate({"command": "does-not-need-to-exist-yet"}))


# --- calling tools -----------------------------------------------------------------------


async def test_a_successful_call_reports_structured_output_and_trace(server_url: str) -> None:
    async with adapter(server_url) as a:
        response = await a.invoke("", call=McpCall(tool="add", arguments={"a": 1, "b": 2}))
    assert response.error is None
    assert response.output == '{"result": 3}'
    assert response.tool_calls_reported
    [call] = [s for s in response.steps if isinstance(s, ToolCallStep)]
    [result] = [s for s in response.steps if isinstance(s, ToolResultStep)]
    assert (call.tool, call.arguments) == ("add", {"a": 1, "b": 2})
    assert result.result == {"result": 3}


async def test_tool_error_is_a_normal_response_not_an_adapter_error(server_url: str) -> None:
    """ToolError is the model's turn to see a message, not an AgentProbe-level failure: the
    tool answered, so the case's judges (not the runner) decide pass/fail on it.
    """
    async with adapter(server_url) as a:
        response = await a.invoke("", call=McpCall(tool="fail_tool_error", arguments={"x": "y"}))
    assert response.error is None
    assert "bad input: y" in response.output


async def test_an_unexpected_crash_never_leaks_its_detail(server_url: str) -> None:
    async with adapter(server_url) as a:
        response = await a.invoke("", call=McpCall(tool="fail_crash", arguments={"x": "y"}))
    assert response.error is None
    assert "internal-detail-never-leaked" not in response.output


async def test_mcp_protocol_error_is_an_adapter_error_not_retried(server_url: str) -> None:
    async with adapter(server_url, max_retries=2) as a:
        response = await a.invoke("", call=McpCall(tool="fail_mcp_error", arguments={"x": "y"}))
    assert response.error is not None
    assert "rejected: y" in response.error
    assert response.retryable is False


async def test_missing_and_wrong_type_arguments_are_rejected_before_the_tool_runs(
    server_url: str,
) -> None:
    async with adapter(server_url) as a:
        missing = await a.invoke("", call=McpCall(tool="add", arguments={"a": 1}))
        wrong_type = await a.invoke("", call=McpCall(tool="add", arguments={"a": "x", "b": 2}))
    assert missing.error is None
    assert "validation error" in missing.output
    assert wrong_type.error is None
    assert "validation error" in wrong_type.output


async def test_an_unknown_tool_is_a_normal_response_not_an_adapter_error(server_url: str) -> None:
    async with adapter(server_url) as a:
        response = await a.invoke("", call=McpCall(tool="no_such_tool", arguments={}))
    assert response.error is None
    assert "no_such_tool" in response.output


async def test_invoke_without_a_call_is_an_error_response(server_url: str) -> None:
    async with adapter(server_url) as a:
        response = await a.invoke("hello")
    assert response.error is not None
    assert "call" in response.error


async def test_connection_succeeds_against_a_real_server(server_url: str) -> None:
    async with adapter(server_url) as a:
        response = await a.test_connection()
    assert response.error is None


# --- failures: SSRF, unreachable, timeout -------------------------------------------------


async def test_a_private_target_is_blocked_without_opt_in() -> None:
    a = McpAdapter(
        McpHttpConfig.model_validate(
            {"url": "http://10.0.0.5:1234/mcp", "timeout_ms": 2000, "max_retries": 0}
        ),
        policy=TargetPolicy(),  # no server-side opt-in
    )
    response = await a.invoke("", call=McpCall(tool="x", arguments={}))
    await a.aclose()
    assert response.error is not None
    assert "private address" in response.error
    assert response.retryable is False


async def test_an_unreachable_server_is_retryable_and_retried() -> None:
    clock = FakeClock()
    a = McpAdapter(
        McpHttpConfig.model_validate(
            {
                "url": "http://127.0.0.1:1/mcp",
                "allow_private": True,
                "timeout_ms": 1000,
                "max_retries": 2,
            }
        ),
        policy=TargetPolicy(allow_private=True),
        clock=clock,
    )
    response = await a.invoke("", call=McpCall(tool="x", arguments={}))
    await a.aclose()
    assert response.retryable is True
    assert response.error is not None
    assert len(clock.sleeps) == 2  # both retries were taken
