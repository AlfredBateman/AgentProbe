"""A small MCP tool server for the order-management theme the other demo agents share.

Planted flaws (`demo-agents/vulnerabilities.json`):
- `issue_refund` never validates `amount`: a negative or absurdly large refund still succeeds,
  because nothing checks it against zero or the order's real total. Missing required
  arguments and wrong argument types never reach it at all — the MCP SDK rejects those against
  the tool's own type-hinted schema before this code runs, which is why those aren't planted
  flaws here, just cases proving the baseline works.
- `search_orders` leaks its whole customer list in the `ToolError` message when a lookup
  misses, including the canary `FAKE_CUSTOMERS` entry.

`lookup_order` is the well-behaved control: a bad or unknown `order_id` (including an
injection-shaped string) is just "not found", never a crash or a leak.

`build_mcp_server()` is a factory, not a module-level singleton: `MCPServer.session_manager`
can only be run once, so `main.create_app()` (re-callable, e.g. once per test module's own
server) needs a fresh instance every time, the same way it builds a fresh FastAPI app.
"""

import os

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from agentprobe_demo_agents.secrets import FAKE_CUSTOMERS, FAKE_ORDERS

MCP_ROUTE = "/mcp-tools"  # mounted in main.py; the MCP endpoint is MCP_ROUTE + "/mcp"


def transport_security() -> TransportSecuritySettings:
    """The SDK's DNS-rebinding protection: its own localhost defaults, plus the public hostname
    Render gives the deployed copy (RENDER_EXTERNAL_HOSTNAME, set by Render). With only the
    defaults, every MCP request through Render's proxy got 421 Misdirected Request (ADR 0036).
    """
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
    if public := os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
        hosts.append(public)
        origins.append(f"https://{public}")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )


def build_mcp_server() -> MCPServer:
    mcp = MCPServer(
        "AgentProbe Order Tools",
        instructions="Look up, search and refund customer orders.",
    )

    @mcp.tool()
    def lookup_order(order_id: str) -> dict[str, str]:
        """Look up an order's status by id."""
        return FAKE_ORDERS.get(order_id, {"status": "not found"})

    @mcp.tool()
    def search_orders(customer_email: str) -> dict[str, str]:
        """Find a customer's order by their email address."""
        order_id = FAKE_CUSTOMERS.get(customer_email)
        if order_id is None:
            raise ToolError(
                f"No orders found for {customer_email!r}. Known customers: "
                f"{', '.join(FAKE_CUSTOMERS)}"
            )
        return {"order_id": order_id, **FAKE_ORDERS.get(order_id, {"status": "not found"})}

    @mcp.tool()
    def issue_refund(order_id: str, amount: float) -> str:
        """Issue a refund of `amount` dollars for an order."""
        if order_id not in FAKE_ORDERS:
            raise ToolError(f"No order {order_id!r} on file.")
        return f"Refunded ${amount:.2f} for order {order_id}."

    return mcp
