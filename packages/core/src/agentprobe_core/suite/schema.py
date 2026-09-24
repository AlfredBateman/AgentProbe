"""Suite YAML schema (SPEC.md §4.1, PLAN.md §2 #9-#10, ADR 0006)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentprobe_core.suite.attacks import is_registered_attack
from agentprobe_core.suite.judges import JudgeSpec

MAX_CASES = 500
MAX_INPUT_LENGTH = 8_000
MIN_RUNS_PER_CASE = 1
MAX_RUNS_PER_CASE = 20


class StatisticsConfig(BaseModel):
    """Regression-test thresholds (ADR 0006). Every field has the ADR's default and can be
    overridden per suite; the CLI can also override them per invocation.
    """

    model_config = ConfigDict(extra="forbid")

    alpha: float = Field(default=0.05, gt=0, lt=1)
    min_drop: float = Field(default=0.05, gt=0, le=1)
    permutation_draws: int = Field(default=10_000, ge=100)
    bootstrap_resamples: int = Field(default=10_000, ge=100)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.-]+$")
    input: str | None = Field(default=None, max_length=MAX_INPUT_LENGTH)
    attack: str | None = None
    attack_params: dict[str, Any] = Field(default_factory=dict)
    obfuscate: bool = False
    mutations: int | None = Field(default=None, ge=1, le=50)
    # Documents/tool output injected into the request template (PLAN.md §2 #11).
    context: list[dict[str, Any]] | None = None
    expect: list[JudgeSpec] = Field(min_length=1)

    @field_validator("attack")
    @classmethod
    def _attack_is_registered(cls, value: str | None) -> str | None:
        if value is not None and not is_registered_attack(value):
            raise ValueError(f"unknown attack id {value!r}; register it first")
        return value

    @model_validator(mode="after")
    def _input_or_attack(self) -> "Case":
        if self.input is None and self.attack is None:
            raise ValueError("a case needs `input`, `attack` (or both)")
        return self


class Suite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: str = Field(min_length=1, max_length=200)
    agent: str = Field(min_length=1, max_length=200)
    runs_per_case: int = Field(default=1, ge=MIN_RUNS_PER_CASE, le=MAX_RUNS_PER_CASE)
    statistics: StatisticsConfig = Field(default_factory=StatisticsConfig)
    cases: list[Case] = Field(min_length=1, max_length=MAX_CASES)

    @field_validator("cases")
    @classmethod
    def _unique_case_ids(cls, cases: list[Case]) -> list[Case]:
        seen: set[str] = set()
        for case in cases:
            if case.id in seen:
                raise ValueError(f"duplicate case id {case.id!r}")
            seen.add(case.id)
        return cases
