"""Thin pass-through to packages/core's LLM client, used when AGENT_MODE=llm. Goes through
the same budget guard and RUN_LIVE gate as everything else in agentprobe_core.llm — a demo
agent is not a special case.
"""

from agentprobe_core.llm import Client, create_client

_client: Client | None = None


async def _get_client() -> Client:
    global _client
    if _client is None:
        _client = await create_client(verify=False)
    return _client


async def complete(system_prompt: str, user_input: str) -> str:
    client = await _get_client()
    result = await client.complete(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        role="agent",
    )
    return result.text
