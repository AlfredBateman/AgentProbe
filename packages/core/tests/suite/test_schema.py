import pytest
from pydantic import ValidationError

from agentprobe_core.suite.schema import Case, StatisticsConfig, Suite

CONTAINS = {"judge": "contains", "value": "ok"}


def make_suite(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "suite": "demo",
        "agent": "demo-bot",
        "runs_per_case": 3,
        "cases": [{"id": "c1", "input": "hi", "expect": [CONTAINS]}],
    }
    base.update(overrides)
    return base


def test_minimal_valid_suite() -> None:
    suite = Suite.model_validate(make_suite())
    assert suite.suite == "demo"
    assert suite.cases[0].id == "c1"
    assert suite.statistics.alpha == 0.05  # ADR 0006 default


def test_statistics_block_overrides() -> None:
    suite = Suite.model_validate(
        make_suite(statistics={"alpha": 0.01, "min_drop": 0.1, "permutation_draws": 500})
    )
    assert suite.statistics.alpha == 0.01
    assert suite.statistics.min_drop == 0.1
    assert suite.statistics.permutation_draws == 500
    assert suite.statistics.bootstrap_resamples == 10_000  # untouched default


def test_statistics_cli_overrides() -> None:
    from_yaml = StatisticsConfig(alpha=0.01, permutation_draws=500)
    # None = flag not given: the YAML value (or default) stays.
    config = from_yaml.override(alpha=None, min_drop=0.1, bootstrap_resamples=None)
    assert (config.alpha, config.min_drop, config.permutation_draws) == (0.01, 0.1, 500)
    assert from_yaml.min_drop == 0.05  # not mutated


@pytest.mark.parametrize("flags", [{"alpha": 1.5}, {"min_drop": 0}, {"bogus": 1}])
def test_statistics_cli_overrides_are_validated(flags: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        StatisticsConfig().override(**flags)


def test_overriding_alpha_resplits_the_budget() -> None:
    # The channel shares are stored as "unset" rather than resolved, so raising alpha with
    # --alpha widens both halves instead of leaving them at the old alpha's split.
    config = StatisticsConfig().override(alpha=0.1)
    assert (config.alpha, config.cases_alpha, config.suite_alpha) == (0.1, 0.05, 0.05)
    # An explicit share survives an alpha override (as long as it still fits the budget).
    pinned = StatisticsConfig(alpha=0.1, alpha_cases=0.09, alpha_suite=0.01).override(alpha=0.2)
    assert (pinned.cases_alpha, pinned.suite_alpha) == (0.09, 0.01)


def test_a_statistics_block_without_the_channel_shares_still_parses() -> None:
    # Run files and suite YAML written before the split carry only `alpha` (ADR 0014).
    old = StatisticsConfig.model_validate({"alpha": 0.05, "min_drop": 0.05})
    assert (old.cases_alpha, old.suite_alpha) == (0.025, 0.025)
    assert StatisticsConfig.model_validate_json(old.model_dump_json()) == old


@pytest.mark.parametrize("runs_per_case", [0, 21])
def test_runs_per_case_bounds(runs_per_case: int) -> None:
    with pytest.raises(ValidationError):
        Suite.model_validate(make_suite(runs_per_case=runs_per_case))


def test_unknown_top_level_key_rejected() -> None:
    with pytest.raises(ValidationError):
        Suite.model_validate(make_suite(unexpected="field"))


def test_unknown_case_key_rejected() -> None:
    with pytest.raises(ValidationError):
        Case.model_validate({"id": "c1", "input": "hi", "expect": [CONTAINS], "bogus": 1})


def test_duplicate_case_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate case id"):
        Suite.model_validate(
            make_suite(
                cases=[
                    {"id": "c1", "input": "a", "expect": [CONTAINS]},
                    {"id": "c1", "input": "b", "expect": [CONTAINS]},
                ]
            )
        )


def test_case_needs_input_or_attack() -> None:
    with pytest.raises(ValidationError):
        Case.model_validate({"id": "c1", "expect": [CONTAINS]})


def test_case_with_only_attack_is_valid() -> None:
    case = Case.model_validate({"id": "c1", "attack": "tool_misuse", "expect": [CONTAINS]})
    assert case.input is None
    assert case.attack == "tool_misuse"


def test_unknown_attack_rejected() -> None:
    with pytest.raises(ValidationError, match=r"unknown attack id 'no\.such\.attack'; known: "):
        Case.model_validate({"id": "c1", "attack": "no.such.attack", "expect": [CONTAINS]})


def test_case_requires_at_least_one_expectation() -> None:
    with pytest.raises(ValidationError):
        Case.model_validate({"id": "c1", "input": "hi", "expect": []})


def test_input_over_max_length_rejected() -> None:
    with pytest.raises(ValidationError):
        Case.model_validate({"id": "c1", "input": "x" * 8_001, "expect": [CONTAINS]})


def test_suite_over_max_cases_rejected() -> None:
    cases = [{"id": f"c{i}", "input": "hi", "expect": [CONTAINS]} for i in range(501)]
    with pytest.raises(ValidationError):
        Suite.model_validate(make_suite(cases=cases))


def test_context_fixtures_round_trip() -> None:
    case = Case.model_validate(
        {
            "id": "c1",
            "input": "hi",
            "context": [{"name": "policy.txt", "content": "refunds within 30 days"}, "plain"],
            "expect": [CONTAINS],
        }
    )
    assert case.context == [{"name": "policy.txt", "content": "refunds within 30 days"}, "plain"]


def test_mutations_field() -> None:
    case = Case.model_validate({"id": "c1", "input": "hi", "mutations": 3, "expect": [CONTAINS]})
    assert case.mutations == 3


def test_obfuscate_defaults_false() -> None:
    case = Case.model_validate({"id": "c1", "input": "hi", "expect": [CONTAINS]})
    assert case.obfuscate is False
