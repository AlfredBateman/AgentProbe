"""Runs every bundled demo agent as one process: `python -m agentprobe_demo_agents` or the
`agentprobe-demo-agents` console script. Binds to localhost only.
"""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "agentprobe_demo_agents.main:app",
        host="127.0.0.1",
        port=int(os.environ.get("DEMO_AGENTS_PORT", "9000")),
    )


if __name__ == "__main__":
    main()
