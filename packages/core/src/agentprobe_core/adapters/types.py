"""Shared adapter types: the trace step model (used by the runner, judges, storage and UI),
the adapter response, and the `AgentAdapter` protocol every adapter implements.

Agent output, tool arguments and tool results are untrusted data: store and show them as
text; never execute them, render them as HTML or let them steer a judge.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue


def _now() -> datetime:
    return datetime.now(UTC)


class _Step(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: AwareDatetime = Field(default_factory=_now)  # when the step started
    duration_ms: float | None = Field(default=None, ge=0)  # None: the agent didn't report it


class MessageStep(_Step):
    type: Literal["message"] = "message"
    role: Literal["system", "user", "assistant"]
    content: str


class ToolCallStep(_Step):
    type: Literal["tool_call"] = "tool_call"
    tool: str
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class ToolResultStep(_Step):
    type: Literal["tool_result"] = "tool_result"
    tool: str
    result: JsonValue = None


class ErrorStep(_Step):
    type: Literal["error"] = "error"
    message: str


TraceStep = Annotated[
    MessageStep | ToolCallStep | ToolResultStep | ErrorStep, Field(discriminator="type")
]


class TokenUsage(BaseModel):
    """The agent's own token usage, as it reports it. None: not reported."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class AgentResponse(BaseModel):
    """One call to the agent under test. A failed call (after retries) has `error` set, an
    `ErrorStep` in `steps` and an empty `output`; adapters return it rather than raising.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    output: str
    steps: list[TraceStep]
    usage: TokenUsage = TokenUsage()
    latency_ms: float = Field(ge=0)
    error: str | None = None
    # False when the agent doesn't report tool calls: "no tool_call steps" then means
    # "unknown", not "none were made", and a tool judge must not pass on it.
    tool_calls_reported: bool = False
    # True when the failure never reached the agent or the agent asked for a retry (connect
    # failure, 429/502/503/504) and the adapter's own retries ran out: the run loop may retry
    # the attempt later. Anything the agent may have acted on stays False.
    retryable: bool = False

    @property
    def tool_calls(self) -> list[ToolCallStep]:
        return [step for step in self.steps if isinstance(step, ToolCallStep)]


class AdapterNotAllowed(Exception):
    """This adapter can't run here (the Python adapter outside the CLI, or an unknown type)."""


class AgentAdapter(Protocol):
    async def invoke(self, input: str, context: Sequence[JsonValue] = ()) -> AgentResponse:
        """Sends one input (plus the case's context documents) to the agent."""
        ...
