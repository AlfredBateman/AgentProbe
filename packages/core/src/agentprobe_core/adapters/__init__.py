"""Agent adapters (SPEC.md §4.2, ADR 0012): the HTTP adapter with its SSRF guard, the MCP
adapter, and `build_adapter` for the server. The protocol and trace step model are in
`.types`.

The Python adapter (`agentprobe_core.adapters.python`) is CLI-only and deliberately not
imported here, so the server never loads it.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import SecretStr

from agentprobe_core.adapters.http import HttpAdapter, HttpAdapterConfig, check_header
from agentprobe_core.adapters.mcp import McpAdapter, McpHttpConfig
from agentprobe_core.adapters.ssrf import TargetPolicy
from agentprobe_core.adapters.types import AdapterNotAllowed


def build_adapter(
    adapter_type: str,
    config: Mapping[str, Any],
    *,
    secret_headers: Mapping[str, SecretStr] | None = None,
    policy: TargetPolicy | None = None,
) -> HttpAdapter | McpAdapter:
    """The server's way to build an adapter from a stored agent. Refuses `python`: it's
    CLI-only, and the CLI constructs `PythonAdapter` itself. `mcp` is validated against
    `McpHttpConfig` only (not the stdio/http union), so a stored `transport: stdio` config —
    which shouldn't exist, since the API's own config model already forbids it — is refused
    here too, as a backstop rather than the only guard.
    """
    if adapter_type == "http":
        return HttpAdapter(
            HttpAdapterConfig.model_validate(config), secret_headers=secret_headers, policy=policy
        )
    if adapter_type == "mcp":
        if config.get("transport") == "stdio":
            raise AdapterNotAllowed(
                "MCP stdio transport is CLI-only; the server can't launch subprocesses"
            )
        return McpAdapter(McpHttpConfig.model_validate(config), policy=policy)
    if adapter_type == "python":
        raise AdapterNotAllowed("the python adapter is CLI-only; the server can't execute it")
    raise AdapterNotAllowed(f"adapter type {adapter_type!r} is not supported yet")


__all__ = [
    "AdapterNotAllowed",
    "HttpAdapter",
    "HttpAdapterConfig",
    "McpAdapter",
    "McpHttpConfig",
    "TargetPolicy",
    "build_adapter",
    "check_header",
]
