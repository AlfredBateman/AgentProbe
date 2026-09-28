"""Read-only view of the LLM role -> model mapping, so Settings never hardcodes a model name."""

from fastapi import APIRouter
from pydantic import BaseModel

from agentprobe_api.auth import CurrentUser
from agentprobe_core.llm import LLMConfig

router = APIRouter(prefix="/config", tags=["config"])


class LlmConfigOut(BaseModel):
    provider: str
    models: dict[str, str]


@router.get("/llm")
async def get_llm_config(_: CurrentUser) -> LlmConfigOut:
    config = LLMConfig.from_env()
    models: dict[str, str] = {role: model for role, model in config.models.items()}
    return LlmConfigOut(provider=config.provider, models=models)
