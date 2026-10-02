"""The MCP route behind Render's proxy (ADR 0036): the public hostname passes the SDK's
DNS-rebinding check, and any other host still doesn't.
"""

import pytest
from fastapi.testclient import TestClient

from agentprobe_demo_agents.main import create_app
from agentprobe_demo_agents.mcp_server import MCP_ROUTE

PUBLIC = "agentprobe-1r00.onrender.com"
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}},
}
HEADERS = {"accept": "application/json, text/event-stream"}


@pytest.mark.parametrize(
    ("host", "origin", "expected"),
    [
        (PUBLIC, None, 200),
        (PUBLIC, f"https://{PUBLIC}", 200),
        ("127.0.0.1:9000", None, 200),
        ("evil.example", None, 421),  # a rebinding attacker's own name
        (PUBLIC, "https://evil.example", 403),
    ],
)
def test_mcp_accepts_render_public_host_only(
    monkeypatch: pytest.MonkeyPatch, host: str, origin: str | None, expected: int
) -> None:
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", PUBLIC)
    headers = HEADERS | {"host": host} | ({"origin": origin} if origin else {})
    with TestClient(create_app()) as client:
        r = client.post(f"{MCP_ROUTE}/mcp", json=INITIALIZE, headers=headers)
    assert r.status_code == expected


def test_without_render_only_localhost_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
    with TestClient(create_app()) as client:
        r = client.post(f"{MCP_ROUTE}/mcp", json=INITIALIZE, headers=HEADERS | {"host": PUBLIC})
    assert r.status_code == 421
