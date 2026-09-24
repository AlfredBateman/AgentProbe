"""The judge interface: `Judgment`, the context a judge runs against, and the registry
protocol every judge (rule-based, `llm_rubric`, `consistency`) implements (SPEC.md §4.5).
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import JsonValue

from agentprobe_core.adapters.types import AgentResponse, TraceStep
from agentprobe_core.llm.types import LLMClient
from agentprobe_core.suite.schema import Case

Status = Literal["pass", "fail", "error"]


@dataclass(frozen=True)
class Judgment:
    """A judge's verdict. `error` means the judge itself couldn't run (missing LLM client,
    unparseable judge response, tool calls not reported, ...) -- never a silent pass or fail.
    """

    status: Status
    score: float  # 0..1; meaningless (but still present) when status == "error"
    reason: str
    evidence: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class JudgeContext:
    """What a judge evaluates against: one attempt's case and agent response.

    `llm` is required by `llm_rubric` and used (optionally) by `consistency`; rule-based
    judges ignore it. `case_outputs` is the consistency judge's input: every attempt's output
    for this case (including this one), supplied by whatever ran the repeated attempts.
    """

    case: Case
    response: AgentResponse
    llm: LLMClient | None = None
    case_outputs: Sequence[str] = ()

    @property
    def input(self) -> str:
        return self.case.input or ""

    @property
    def output(self) -> str:
        return self.response.output

    @property
    def steps(self) -> Sequence[TraceStep]:
        return self.response.steps

    @property
    def latency_ms(self) -> float:
        return self.response.latency_ms


# The spec parameter is `Any` here (each judge function narrows it to its own spec type) so
# heterogeneous judge functions can share one registry without a variance error under mypy
# strict: a `Callable[[ContainsJudge, ...], ...]` isn't a subtype of `Callable[[JudgeSpec, ...],
# ...]`, but every concrete judge function *is* assignable to a parameter typed `Any`.
JudgeFn = Callable[[Any, JudgeContext], Awaitable[Judgment]]


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
