import pytest
from pydantic import TypeAdapter

from agentprobe_core.judges import REGISTRY, evaluate
from agentprobe_core.suite.judges import JudgeSpec
from judgefakes import make_ctx, make_response

_ADAPTER: TypeAdapter[object] = TypeAdapter(JudgeSpec)

# One example spec per judge name, covering every entry the suite schema can discriminate on.
_SPECS = {
    "contains": {"judge": "contains", "value": "x"},
    "contains_any": {"judge": "contains_any", "values": ["x"]},
    "not_contains": {"judge": "not_contains", "values": ["x"]},
    "regex": {"judge": "regex", "pattern": "x"},
    "json_schema": {"judge": "json_schema", "schema": {"type": "object"}},
    "max_length": {"judge": "max_length", "max_chars": 10},
    "latency_under": {"judge": "latency_under", "ms": 1000},
    "tool_called": {"judge": "tool_called", "tool": "t"},
    "tool_not_called": {"judge": "tool_not_called", "tool": "t"},
    "tool_args_match": {"judge": "tool_args_match", "tool": "t", "args": {"a": 1}},
    "llm_rubric": {"judge": "llm_rubric", "rubric": "x"},
    "consistency": {"judge": "consistency"},
}


def test_registry_covers_every_judge_name_in_the_schema() -> None:
    assert set(REGISTRY) == set(_SPECS)


@pytest.mark.parametrize("name", sorted(_SPECS))
async def test_evaluate_dispatches_by_judge_name(name: str) -> None:
    assert REGISTRY[name].__name__ == name  # e.g. "not_contains" isn't wired to `contains`
    spec = _ADAPTER.validate_python(_SPECS[name])
    ctx = make_ctx(response=make_response("x"))
    assert await evaluate(spec, ctx) == await REGISTRY[name](spec, ctx)  # type: ignore[arg-type]
