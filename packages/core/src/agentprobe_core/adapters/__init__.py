"""Agent adapters (SPEC.md §4.2, ADR 0012): the HTTP adapter with its SSRF guard, and
`build_adapter` for the server. The protocol and trace step model are in `.types`.

The Python adapter (`agentprobe_core.adapters.python`) is CLI-only and deliberately not
imported here, so the server never loads it.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import SecretStr

from agentprobe_core.adapters.http import HttpAdapter, HttpAdapterConfig, check_header
from agentprobe_core.adapters.ssrf import TargetPolicy
from agentprobe_core.adapters.types import AdapterNotAllowed


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
    "AdapterNotAllowed",
    "HttpAdapter",
    "HttpAdapterConfig",
    "TargetPolicy",
    "build_adapter",
    "check_header",
]
