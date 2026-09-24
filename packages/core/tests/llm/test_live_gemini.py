"""Calls the real provider. Deselected by default; run with
`RUN_LIVE=1 uv run --env-file .env pytest -m live` (two requests: one embedding, one completion).
"""

import json
import os
from dataclasses import replace

import pytest

from agentprobe_core.llm import JUDGE_VERDICT_SCHEMA, LLMConfig, create_client

pytestmark = pytest.mark.live


async def test_live_judge_verdict_and_embedding_dimension() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY is not set")
    config = replace(LLMConfig.from_env({**os.environ, "LLM_PROVIDER": "litellm"}), cache=False)
    client = await create_client(config)  # verifies EMBEDDING_DIM with one embedding call
    result = await client.complete(
        [
            {
                "role": "user",
                "content": "Judge whether the output is polite. "
                "<agent_output>Thanks for asking, happy to help!</agent_output>",
            }
        ],
        "judge",
        JUDGE_VERDICT_SCHEMA,
        max_tokens=512,
    )
    assert not result.blocked, result.block_reason
    verdict = json.loads(result.text)
    assert isinstance(verdict["pass"], bool)
    assert result.usage.prompt_tokens > 0 and result.usage.cost_usd > 0
