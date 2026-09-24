"""Judge specs (SPEC.md §4.5): what a case's `expect:` list can contain.

A discriminated union keyed by `judge`. Each spec only describes *what to check*; the judge
implementations (running the check against a run's output/trace) come in Prompt 8's follow-up
work, not here.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _JudgeSpecBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- rule-based judges (SPEC.md §4.5) --------------------------------------------------


class ContainsJudge(_JudgeSpecBase):
    judge: Literal["contains"]
    value: str = Field(min_length=1)


class ContainsAnyJudge(_JudgeSpecBase):
    judge: Literal["contains_any"]
    values: list[str] = Field(min_length=1)


class NotContainsJudge(_JudgeSpecBase):
    judge: Literal["not_contains"]
    values: list[str] = Field(min_length=1)


class RegexJudge(_JudgeSpecBase):
    judge: Literal["regex"]
    pattern: str = Field(min_length=1)
    flags: str = ""  # e.g. "i" for case-insensitive; validated by the judge implementation


class JsonSchemaJudge(_JudgeSpecBase):
    judge: Literal["json_schema"]
    schema_: dict[str, Any] = Field(alias="schema")


class MaxLengthJudge(_JudgeSpecBase):
    judge: Literal["max_length"]
    max_chars: int = Field(gt=0)


class LatencyUnderJudge(_JudgeSpecBase):
    judge: Literal["latency_under"]
    ms: int = Field(gt=0)


class ToolCalledJudge(_JudgeSpecBase):
    judge: Literal["tool_called"]
    tool: str = Field(min_length=1)


class ToolNotCalledJudge(_JudgeSpecBase):
    judge: Literal["tool_not_called"]
    tool: str = Field(min_length=1)


class ToolArgsMatchJudge(_JudgeSpecBase):
    judge: Literal["tool_args_match"]
    tool: str = Field(min_length=1)
    args: dict[str, Any] = Field(min_length=1)


# --- LLM and cross-run judges -----------------------------------------------------------


class LlmRubricJudge(_JudgeSpecBase):
    judge: Literal["llm_rubric"]
    rubric: str = Field(min_length=1)


class ConsistencyJudge(_JudgeSpecBase):
    judge: Literal["consistency"]
    min_agreement: float = Field(default=1.0, ge=0, le=1)


JudgeSpec = Annotated[
    ContainsJudge
    | ContainsAnyJudge
    | NotContainsJudge
    | RegexJudge
    | JsonSchemaJudge
    | MaxLengthJudge
    | LatencyUnderJudge
    | ToolCalledJudge
    | ToolNotCalledJudge
    | ToolArgsMatchJudge
    | LlmRubricJudge
    | ConsistencyJudge,
    Field(discriminator="judge"),
]
