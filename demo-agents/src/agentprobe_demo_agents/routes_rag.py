"""The RAG doc-QA bot. Its response uses a different JSON shape than support/vulnerable
(`result.text` / `meta.*` instead of top-level `output`), so the future HTTP adapter's
response mapping is genuinely exercised against more than one layout.
"""

import os

from fastapi import APIRouter

from agentprobe_demo_agents import llm_agent, rag
from agentprobe_demo_agents.schemas import AgentRequest, RagResponse

_SYSTEM_PROMPT = "You are a document-QA assistant. Answer only from the retrieved documents."

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/chat", response_model=RagResponse)
async def chat(req: AgentRequest) -> RagResponse:
    if os.environ.get("AGENT_MODE", "mock") == "llm":
        output = await llm_agent.complete(_SYSTEM_PROMPT, req.input)
        return RagResponse(result={"text": output}, meta={})
    return RagResponse(**rag.answer(req.input, req.context))
