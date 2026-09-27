"""Runs the demo MCP server (`mcp_server.build_mcp_server`) over stdio instead of Streamable
HTTP, for testing the CLI's stdio transport (ADR 0023: stdio is CLI-only, since it means
launching an arbitrary local command). Same tools, same planted flaws, as `/mcp-tools`.

    python -m agentprobe_demo_agents.mcp_stdio
"""

import asyncio

from agentprobe_demo_agents.mcp_server import build_mcp_server


def main() -> None:
    asyncio.run(build_mcp_server().run_stdio_async())


if __name__ == "__main__":
    main()
