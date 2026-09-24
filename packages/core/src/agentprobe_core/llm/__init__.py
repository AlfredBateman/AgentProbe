"""LLM layer: role -> model config, mock (default) and LiteLLM providers, rate limits, daily
quota, backoff, per-run budget, disk cache and usage accounting.
"""

from agentprobe_core.llm.client import Client, create_client
from agentprobe_core.llm.config import LLMConfig, Price
from agentprobe_core.llm.mock import CANARY_PATTERN, Fixture, MockProvider
from agentprobe_core.llm.types import (
    AGENT_OUTPUT_TAG,
    JUDGE_VERDICT_SCHEMA,
    ROLES,
    BudgetExceeded,
    Completion,
    EmbeddingDimensionMismatch,
    Embeddings,
    LLMClient,
    LLMConfigError,
    LLMError,
    Message,
    QuotaExhausted,
    Role,
    TransientLLMError,
    Usage,
)

__all__ = [
    "AGENT_OUTPUT_TAG",
    "CANARY_PATTERN",
    "JUDGE_VERDICT_SCHEMA",
    "ROLES",
    "BudgetExceeded",
    "Client",
    "Completion",
    "EmbeddingDimensionMismatch",
    "Embeddings",
    "Fixture",
    "LLMClient",
    "LLMConfig",
    "LLMConfigError",
    "LLMError",
    "Message",
    "MockProvider",
    "Price",
    "QuotaExhausted",
    "Role",
    "TransientLLMError",
    "Usage",
    "create_client",
]
