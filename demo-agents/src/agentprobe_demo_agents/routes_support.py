"""Routes for /support/v1 and /support/v2: identical code, different prompt files.

The prompt file is re-read on every request (no caching), so editing it — including a live
edit while the process is running — genuinely changes behavior.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Header

from agentprobe_demo_agents import llm_agent
from agentprobe_demo_agents.engine import SupportConfig, run_support
from agentprobe_demo_agents.prompts import load_prompt, refund_window_days
from agentprobe_demo_agents.schemas import AgentRequest, ChatResponse

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def build_router(version: str) -> APIRouter:
    router = APIRouter(prefix=f"/support/{version}", tags=[f"support-{version}"])
    prompt_path = PROMPTS_DIR / f"support_{version}.md"

    @router.post("/chat", response_model=ChatResponse)
    async def chat(req: AgentRequest, x_admin_context: bool = Header(False)) -> ChatResponse:
        prompt_text = load_prompt(prompt_path)
        if os.environ.get("AGENT_MODE", "mock") == "llm":
            return ChatResponse(output=await llm_agent.complete(prompt_text, req.input))
        cfg = SupportConfig(
            system_prompt=prompt_text,
            refund_window_days=refund_window_days(prompt_text),
            apply_flaky=True,
        )
        return ChatResponse(**run_support(req.input, is_admin=x_admin_context, cfg=cfg))

    return router
