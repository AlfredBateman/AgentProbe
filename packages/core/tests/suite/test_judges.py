import pytest
from pydantic import TypeAdapter, ValidationError

from agentprobe_core.suite.judges import JudgeSpec

adapter: TypeAdapter[object] = TypeAdapter(JudgeSpec)

VALID = [
    {"judge": "contains", "value": "hello"},
    {"judge": "contains_any", "values": ["a", "b"]},
    {"judge": "not_contains", "values": ["secret"]},
    {"judge": "regex", "pattern": r"\d+"},
    {"judge": "json_schema", "schema": {"type": "object"}},
    {"judge": "max_length", "max_chars": 100},
    {"judge": "latency_under", "ms": 2000},
    {"judge": "tool_called", "tool": "lookup_order"},
    {"judge": "tool_not_called", "tool": "delete_order"},
    {"judge": "tool_args_match", "tool": "refund", "args": {"amount": 10}},
    {"judge": "llm_rubric", "rubric": "must refuse"},
    {"judge": "consistency"},
]


@pytest.mark.parametrize("payload", VALID, ids=[p["judge"] for p in VALID])
def test_valid_judge_specs_parse(payload: dict[str, object]) -> None:
    spec = adapter.validate_python(payload)
    assert spec.judge == payload["judge"]  # type: ignore[attr-defined]


def test_unknown_judge_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python({"judge": "does_not_exist"})


def test_missing_required_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python({"judge": "contains"})  # no `value`


def test_unknown_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python({"judge": "contains", "value": "x", "surprise": 1})


def test_consistency_judge_default_agreement() -> None:
    spec = adapter.validate_python({"judge": "consistency"})
    assert spec.min_agreement == 1.0  # type: ignore[attr-defined]
