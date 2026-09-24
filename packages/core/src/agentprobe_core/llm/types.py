"""Shared types for the LLM layer: roles, messages, results, errors and the client protocol."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypedDict

Role = Literal["agent", "judge", "attacker", "summarizer", "embedding"]
ROLES: tuple[Role, ...] = ("agent", "judge", "attacker", "summarizer", "embedding")

# The judge's structured verdict (SPEC.md §4.5). Judge prompts wrap the text under judgment in
# <agent_output>…</agent_output> so it's delimited as data; the mock judge reads the same tags.
AGENT_OUTPUT_TAG = "agent_output"
JUDGE_VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pass": {"type": "boolean"},
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
    },
    "required": ["pass", "score", "reason"],
}


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    finish_reason: str | None = None
    # A provider safety block is a result, not an exception: callers record it and move on.
    blocked: bool = False
    block_reason: str | None = None
    usage: Usage = field(default_factory=Usage)
    cached: bool = False
    latency_ms: float = 0.0


@dataclass(frozen=True)
class Embeddings:
    vectors: list[list[float]]
    model: str
    usage: Usage = field(default_factory=Usage)
    cached: bool = False
    latency_ms: float = 0.0


class LLMError(Exception):
    pass


class LLMConfigError(LLMError):
    pass


class EmbeddingDimensionMismatch(LLMConfigError):
    pass


class BudgetExceeded(LLMError):
    """The per-run budget (calls, tokens, USD) or the per-day USD cap is used up."""


class QuotaExhausted(LLMError):
    """The daily request limit (LLM_RPD, or the provider's own) is used up."""


class TransientLLMError(LLMError):
    """A 429/5xx/timeout a provider raises for the client to retry with backoff."""

    def __init__(self, message: str, *, status: int | None, retry_after: float | None) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class LLMClient(Protocol):
    async def complete(
        self,
        messages: Sequence[Message],
        role: Role,
        json_schema: dict[str, Any] | None = None,
        *,
        temperature: float | None = None,
        max_tokens: int = 1024,
    ) -> Completion: ...

    async def embed(self, texts: Sequence[str]) -> Embeddings: ...


class Provider(Protocol):
    """A backend (mock or LiteLLM). The client wraps it with cache, limits, retries, budget."""

    async def complete(
        self,
        model: str,
        messages: Sequence[Message],
        *,
        role: Role,
        json_schema: dict[str, Any] | None,
        temperature: float | None,
        max_tokens: int,
    ) -> Completion: ...

    async def embed(self, model: str, texts: Sequence[str], *, dimensions: int) -> Embeddings: ...
