from dataclasses import dataclass, field
from typing import Any

from agentprobe_core.adapters.types import AgentResponse, ToolCallStep
from agentprobe_core.judges.types import JudgeContext
from agentprobe_core.llm.types import Completion, Embeddings, Message
from agentprobe_core.suite.schema import Case


def make_case(**overrides: object) -> Case:
    defaults: dict[str, object] = {
        "id": "case-1",
        "input": "hello",
        "expect": [{"judge": "max_length", "max_chars": 10_000}],
    }
    defaults.update(overrides)
    return Case.model_validate(defaults)


def make_response(
    output: str = "",
    *,
    steps: list[object] | None = None,
    latency_ms: float = 100.0,
    tool_calls_reported: bool = False,
) -> AgentResponse:
    return AgentResponse(
        output=output,
        steps=steps or [],
        latency_ms=latency_ms,
        tool_calls_reported=tool_calls_reported,
    )


def make_ctx(
    *,
    case: Case | None = None,
    response: AgentResponse | None = None,
    llm: Any = None,
    case_outputs: tuple[str, ...] = (),
) -> JudgeContext:
    return JudgeContext(
        case=case or make_case(),
        response=response or make_response(),
        llm=llm,
        case_outputs=case_outputs,
    )


def tool_call(tool: str, **arguments: object) -> ToolCallStep:
    return ToolCallStep(tool=tool, arguments=arguments)


@dataclass
class ScriptedLLM:
    """A minimal `LLMClient` double for judge tests that need exact control over verdicts or
    embedding vectors, rather than the mock provider's content-based heuristics: one
    `Completion` is consumed per `complete()` call (in order), and every `embed()` call
    returns the same fixed vectors.
    """

    completions: list[Completion] = field(default_factory=list)
    embedding_vectors: list[list[float]] | None = None
    complete_calls: list[list[Message]] = field(default_factory=list)
    embed_calls: list[list[str]] = field(default_factory=list)

    async def complete(
        self,
        messages: list[Message],
        role: str,
        json_schema: dict[str, Any] | None = None,
        *,
        temperature: float | None = None,
        max_tokens: int = 1024,
    ) -> Completion:
        self.complete_calls.append(list(messages))
        return self.completions[len(self.complete_calls) - 1]

    async def embed(self, texts: list[str]) -> Embeddings:
        self.embed_calls.append(list(texts))
        assert self.embedding_vectors is not None, "ScriptedLLM.embedding_vectors not set"
        return Embeddings(vectors=self.embedding_vectors, model="mock/embedding")
