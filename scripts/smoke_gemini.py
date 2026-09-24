"""Live smoke test: exactly one small completion and one embedding call against Gemini.

    RUN_LIVE=1 uv run python scripts/smoke_gemini.py

Reads .env (without overriding variables already set in the shell), forces
LLM_PROVIDER=litellm, and goes through the normal client: rate limits, budget, pricing.
Prints latency, tokens, estimated cost and the embedding dimension. Exits non-zero on failure.
"""

import asyncio
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from agentprobe_core.llm import JUDGE_VERDICT_SCHEMA, LLMConfig, LLMError, create_client


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, _, value = line.partition("=")
            os.environ.setdefault(name.strip(), value.strip())


async def main() -> int:
    load_dotenv(Path(".env"))
    if os.environ.get("RUN_LIVE") != "1":
        print("Refusing to call a live LLM: set RUN_LIVE=1.", file=sys.stderr)
        return 2
    os.environ["LLM_PROVIDER"] = "litellm"
    config = replace(LLMConfig.from_env(), cache=False)  # a smoke test must hit the provider
    client = await create_client(config, verify=False)  # the embed call below is the check

    judge = await client.complete(
        [
            {
                "role": "user",
                "content": "Is this reply polite? Answer as JSON. "
                "<agent_output>Thanks for asking, happy to help!</agent_output>",
            }
        ],
        "judge",
        JUDGE_VERDICT_SCHEMA,
        max_tokens=512,
    )
    print(f"completion  model={judge.model}")
    print(f"            latency={judge.latency_ms:.0f} ms  finish_reason={judge.finish_reason}")
    print(
        f"            tokens in={judge.usage.prompt_tokens} out={judge.usage.completion_tokens}"
        f"  est. cost=${judge.usage.cost_usd:.6f}  blocked={judge.blocked}"
    )
    print(f"            text={judge.text!r}")
    json.loads(judge.text)  # the structured-output path must return valid JSON

    emb = await client.embed(["AgentProbe smoke test: a short sentence to embed."])
    print(f"embedding   model={emb.model}")
    print(f"            latency={emb.latency_ms:.0f} ms  tokens in={emb.usage.prompt_tokens}")
    print(f"            dimension={len(emb.vectors[0])} (EMBEDDING_DIM={config.embedding_dim})")
    print(f"run budget  calls={client.budget.calls} tokens={client.budget.tokens}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except (LLMError, json.JSONDecodeError) as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
