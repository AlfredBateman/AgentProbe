"""Agent adapters (SPEC.md §4.2, ADR 0012): the `AgentAdapter` protocol, the shared trace
step model, and the HTTP adapter with its SSRF guard.

The Python adapter (`agentprobe_core.adapters.python`) is CLI-only and deliberately not
imported here, so the server never loads it.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import SecretStr

from agentprobe_core.adapters.http import (
    DEFAULT_TEMPLATE,
    MAX_REDIRECTS,
    MAX_RESPONSE_BYTES,
    PROBE_INPUT,
    HttpAdapter,
    HttpAdapterConfig,
    ResponseMapping,
    check_header,
    compile_path,
    render_template,
    resolve_path,
)
from agentprobe_core.adapters.ssrf import (
    AddressClass,
    GuardedBackend,
    TargetBlocked,
    TargetPolicy,
    classify,
)
from agentprobe_core.adapters.types import (
    AdapterNotAllowed,
    AgentAdapter,
    AgentResponse,
    ErrorStep,
    MessageStep,
    TokenUsage,
    ToolCallStep,
    ToolResultStep,
    TraceStep,
)


def build_adapter(
    adapter_type: str,
    config: Mapping[str, Any],
    *,
    secret_headers: Mapping[str, SecretStr] | None = None,
    policy: TargetPolicy | None = None,
) -> HttpAdapter:
    """The server's way to build an adapter from a stored agent. Refuses `python`: it's
    CLI-only, and the CLI constructs `PythonAdapter` itself.
    """
    if adapter_type == "http":
        return HttpAdapter(
            HttpAdapterConfig.model_validate(config), secret_headers=secret_headers, policy=policy
        )
    if adapter_type == "python":
        raise AdapterNotAllowed("the python adapter is CLI-only; the server can't execute it")
    raise AdapterNotAllowed(f"adapter type {adapter_type!r} is not supported yet")


__all__ = [
    "DEFAULT_TEMPLATE",
    "MAX_REDIRECTS",
    "MAX_RESPONSE_BYTES",
    "PROBE_INPUT",
    "AdapterNotAllowed",
    "AddressClass",
    "AgentAdapter",
    "AgentResponse",
    "ErrorStep",
    "GuardedBackend",
    "HttpAdapter",
    "HttpAdapterConfig",
    "MessageStep",
    "ResponseMapping",
    "TargetBlocked",
    "TargetPolicy",
    "TokenUsage",
    "ToolCallStep",
    "ToolResultStep",
    "TraceStep",
    "build_adapter",
    "check_header",
    "classify",
    "compile_path",
    "render_template",
    "resolve_path",
]
