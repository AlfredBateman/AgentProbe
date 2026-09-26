"""Suite YAML schema (SPEC.md §4.1, PLAN.md §2 #9-#10, ADR 0006)."""

from fractions import Fraction
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentprobe_core.suite.attacks import ATTACKS
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

    # The whole verdict's false-alarm budget: the rate at which an unchanged agent is called
    # a regression.
    alpha: float = Field(default=0.05, gt=0, lt=1)
    # A verdict fires when the per-case family OR the suite test does, so `alpha` is split
    # between them (Bonferroni, ADR 0014 §Verdict): half each unless set here. Their sum may
    # not exceed `alpha`, since that is what keeps the verdict's own rate at `alpha`. Raise
    # `alpha` to buy more power for both; set these to spend the budget unevenly (for
    # example all of it on the per-case family, with `alpha_suite` left tiny).
    alpha_cases: float | None = Field(default=None, gt=0, lt=1)
    alpha_suite: float | None = Field(default=None, gt=0, lt=1)
    min_drop: float = Field(default=0.05, gt=0, le=1)
    permutation_draws: int = Field(default=10_000, ge=100)
    bootstrap_resamples: int = Field(default=10_000, ge=100)

    @property
    def cases_alpha(self) -> float:
        """The per-case family's share of the budget."""
        return self.alpha / 2 if self.alpha_cases is None else self.alpha_cases

    @property
    def suite_alpha(self) -> float:
        """The suite test's share of the budget."""
        return self.alpha / 2 if self.alpha_suite is None else self.alpha_suite

    @model_validator(mode="after")
    def _within_budget(self) -> "StatisticsConfig":
        # Exact decimal arithmetic, like the threshold comparisons themselves: 0.025 + 0.025
        # must count as exactly 0.05, not the float a hair above it.
        spent = Fraction(repr(self.cases_alpha)) + Fraction(repr(self.suite_alpha))
        if spent > Fraction(repr(self.alpha)):
            raise ValueError(
                f"alpha_cases ({self.cases_alpha:g}) + alpha_suite ({self.suite_alpha:g}) = "
                f"{float(spent):g} is more than alpha ({self.alpha:g}), so the verdict's "
                "false-alarm rate would exceed alpha; raise alpha instead"
            )
        return self

    def override(self, **flags: float | None) -> "StatisticsConfig":
        """This config with CLI flags applied on top. None means the flag wasn't given; the
        result is validated like the YAML block (unknown names and out-of-range values raise).
        """
        given = {name: value for name, value in flags.items() if value is not None}
        return StatisticsConfig.model_validate(self.model_dump() | given)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.-]+$")
    input: str | None = Field(default=None, max_length=MAX_INPUT_LENGTH)
    attack: str | None = None
    attack_params: dict[str, Any] = Field(default_factory=dict)
    obfuscate: bool = False
    mutations: int | None = Field(default=None, ge=1, le=50)
    # Documents/tool output for the request template's {{documents}} (PLAN.md §2 #11): plain
    # text or JSON objects, passed through as-is (ADR 0012).
    context: list[str | dict[str, Any]] | None = None
    expect: list[JudgeSpec] = Field(min_length=1)

    @field_validator("attack")
    @classmethod
    def _attack_is_known(cls, value: str | None) -> str | None:
        if value is not None and value not in ATTACKS:
            raise ValueError(f"unknown attack id {value!r}; known: {', '.join(sorted(ATTACKS))}")
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
