import pytest
from pydantic import ValidationError

from agentprobe_core.suite.attacks import register_attack
from agentprobe_core.suite.schema import Case, Suite

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
    register_attack("test.placeholder")
    case = Case.model_validate({"id": "c1", "attack": "test.placeholder", "expect": [CONTAINS]})
    assert case.input is None
    assert case.attack == "test.placeholder"


def test_unregistered_attack_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown attack id"):
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
