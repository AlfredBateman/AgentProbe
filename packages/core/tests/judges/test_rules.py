import pytest

from agentprobe_core.judges import rules
from agentprobe_core.suite.judges import (
    ContainsAnyJudge,
    ContainsJudge,
    JsonSchemaJudge,
    LatencyUnderJudge,
    MaxLengthJudge,
    NotContainsJudge,
    RegexJudge,
    ToolArgsMatchJudge,
    ToolCalledJudge,
    ToolNotCalledJudge,
)
from judgefakes import make_ctx, make_response, tool_call

# --- contains / contains_any / not_contains -------------------------------------------------


async def test_contains_passes_on_substring() -> None:
    ctx = make_ctx(response=make_response("the answer is 42"))
    result = await rules.contains(ContainsJudge(judge="contains", value="answer"), ctx)
    assert result.status == "pass"
    assert result.score == 1.0


async def test_contains_fails_when_absent() -> None:
    ctx = make_ctx(response=make_response("nope"))
    result = await rules.contains(ContainsJudge(judge="contains", value="answer"), ctx)
    assert result.status == "fail"
    assert result.score == 0.0


async def test_contains_any_reports_first_match() -> None:
    ctx = make_ctx(response=make_response("hello world"))
    spec = ContainsAnyJudge(judge="contains_any", values=["world", "moon"])
    result = await rules.contains_any(spec, ctx)
    assert result.status == "pass"
    assert result.evidence["matched"] == ["world"]


async def test_contains_any_fails_when_none_match() -> None:
    ctx = make_ctx(response=make_response("hello"))
    spec = ContainsAnyJudge(judge="contains_any", values=["a", "b"])
    result = await rules.contains_any(spec, ctx)
    assert result.status == "fail"
    assert result.evidence["matched"] == []


async def test_not_contains_fails_when_forbidden_value_present() -> None:
    ctx = make_ctx(response=make_response("here is the secret key"))
    spec = NotContainsJudge(judge="not_contains", values=["secret"])
    result = await rules.not_contains(spec, ctx)
    assert result.status == "fail"
    assert result.evidence["matched"] == ["secret"]


async def test_not_contains_passes_when_clean() -> None:
    ctx = make_ctx(response=make_response("nothing to see here"))
    spec = NotContainsJudge(judge="not_contains", values=["secret"])
    result = await rules.not_contains(spec, ctx)
    assert result.status == "pass"
    assert result.score == 1.0


# --- regex ------------------------------------------------------------------------------------


async def test_regex_passes_on_match() -> None:
    ctx = make_ctx(response=make_response("order #1234 confirmed"))
    spec = RegexJudge(judge="regex", pattern=r"#\d+")
    result = await rules.regex(spec, ctx)
    assert result.status == "pass"


async def test_regex_fails_on_no_match() -> None:
    ctx = make_ctx(response=make_response("no order here"))
    spec = RegexJudge(judge="regex", pattern=r"#\d+")
    result = await rules.regex(spec, ctx)
    assert result.status == "fail"


async def test_regex_case_insensitive_flag() -> None:
    ctx = make_ctx(response=make_response("REFUND issued"))
    spec = RegexJudge(judge="regex", pattern="refund", flags="i")
    result = await rules.regex(spec, ctx)
    assert result.status == "pass"


async def test_regex_invalid_pattern_is_an_error() -> None:
    ctx = make_ctx(response=make_response("anything"))
    spec = RegexJudge(judge="regex", pattern="(unclosed")
    result = await rules.regex(spec, ctx)
    assert result.status == "error"


async def test_regex_unknown_flag_is_an_error() -> None:
    ctx = make_ctx(response=make_response("anything"))
    spec = RegexJudge(judge="regex", pattern="a", flags="z")
    result = await rules.regex(spec, ctx)
    assert result.status == "error"


async def test_regex_long_input_is_truncated_not_hung(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rules, "MAX_REGEX_INPUT", 10)
    ctx = make_ctx(response=make_response("x" * 50 + "needle"))
    spec = RegexJudge(judge="regex", pattern="needle")
    result = await rules.regex(spec, ctx)
    assert result.status == "fail"  # needle is past the truncation point
    assert result.evidence["truncated"] is True


# --- json_schema ------------------------------------------------------------------------------


async def test_json_schema_passes_on_matching_instance() -> None:
    ctx = make_ctx(response=make_response('{"ok": true}'))
    spec = JsonSchemaJudge.model_validate(
        {"judge": "json_schema", "schema": {"type": "object", "required": ["ok"]}}
    )
    result = await rules.json_schema(spec, ctx)
    assert result.status == "pass"


async def test_json_schema_fails_on_malformed_json() -> None:
    ctx = make_ctx(response=make_response("not json"))
    spec = JsonSchemaJudge.model_validate({"judge": "json_schema", "schema": {"type": "object"}})
    result = await rules.json_schema(spec, ctx)
    assert result.status == "fail"


async def test_json_schema_fails_on_schema_mismatch() -> None:
    ctx = make_ctx(response=make_response("[]"))
    spec = JsonSchemaJudge.model_validate({"judge": "json_schema", "schema": {"type": "object"}})
    result = await rules.json_schema(spec, ctx)
    assert result.status == "fail"
    assert result.evidence["path"] == []


async def test_json_schema_invalid_schema_itself_is_an_error() -> None:
    ctx = make_ctx(response=make_response("{}"))
    spec = JsonSchemaJudge.model_validate(
        {"judge": "json_schema", "schema": {"type": "not-a-real-type"}}
    )
    result = await rules.json_schema(spec, ctx)
    assert result.status == "error"


# --- max_length / latency_under ----------------------------------------------------------------


async def test_max_length_passes_within_limit() -> None:
    ctx = make_ctx(response=make_response("short"))
    result = await rules.max_length(MaxLengthJudge(judge="max_length", max_chars=10), ctx)
    assert result.status == "pass"


async def test_max_length_fails_over_limit() -> None:
    ctx = make_ctx(response=make_response("this is way too long"))
    result = await rules.max_length(MaxLengthJudge(judge="max_length", max_chars=5), ctx)
    assert result.status == "fail"
    assert result.evidence["length"] == 20


async def test_latency_under_passes() -> None:
    ctx = make_ctx(response=make_response("hi", latency_ms=50))
    result = await rules.latency_under(LatencyUnderJudge(judge="latency_under", ms=100), ctx)
    assert result.status == "pass"


async def test_latency_under_fails_at_or_over_the_bound() -> None:
    ctx = make_ctx(response=make_response("hi", latency_ms=100))
    result = await rules.latency_under(LatencyUnderJudge(judge="latency_under", ms=100), ctx)
    assert result.status == "fail"


# --- tool judges: tool_calls_reported gating ----------------------------------------------------


async def test_tool_called_is_an_error_when_not_reported() -> None:
    ctx = make_ctx(response=make_response(tool_calls_reported=False))
    result = await rules.tool_called(ToolCalledJudge(judge="tool_called", tool="refund"), ctx)
    assert result.status == "error"


async def test_tool_called_passes_when_called() -> None:
    response = make_response(steps=[tool_call("refund", order_id=1)], tool_calls_reported=True)
    ctx = make_ctx(response=response)
    result = await rules.tool_called(ToolCalledJudge(judge="tool_called", tool="refund"), ctx)
    assert result.status == "pass"


async def test_tool_called_fails_when_a_different_tool_was_called() -> None:
    response = make_response(steps=[tool_call("lookup")], tool_calls_reported=True)
    ctx = make_ctx(response=response)
    result = await rules.tool_called(ToolCalledJudge(judge="tool_called", tool="refund"), ctx)
    assert result.status == "fail"


async def test_tool_not_called_is_an_error_when_not_reported() -> None:
    ctx = make_ctx(response=make_response(tool_calls_reported=False))
    spec = ToolNotCalledJudge(judge="tool_not_called", tool="delete_order")
    result = await rules.tool_not_called(spec, ctx)
    assert result.status == "error"


async def test_tool_not_called_passes_when_absent() -> None:
    response = make_response(steps=[tool_call("lookup")], tool_calls_reported=True)
    ctx = make_ctx(response=response)
    spec = ToolNotCalledJudge(judge="tool_not_called", tool="delete_order")
    result = await rules.tool_not_called(spec, ctx)
    assert result.status == "pass"


async def test_tool_not_called_fails_when_called() -> None:
    response = make_response(steps=[tool_call("delete_order")], tool_calls_reported=True)
    ctx = make_ctx(response=response)
    spec = ToolNotCalledJudge(judge="tool_not_called", tool="delete_order")
    result = await rules.tool_not_called(spec, ctx)
    assert result.status == "fail"


async def test_tool_args_match_is_an_error_when_not_reported() -> None:
    ctx = make_ctx(response=make_response(tool_calls_reported=False))
    spec = ToolArgsMatchJudge(judge="tool_args_match", tool="refund", args={"amount": 10})
    result = await rules.tool_args_match(spec, ctx)
    assert result.status == "error"


async def test_tool_args_match_fails_when_tool_never_called() -> None:
    response = make_response(steps=[tool_call("lookup")], tool_calls_reported=True)
    ctx = make_ctx(response=response)
    spec = ToolArgsMatchJudge(judge="tool_args_match", tool="refund", args={"amount": 10})
    result = await rules.tool_args_match(spec, ctx)
    assert result.status == "fail"


async def test_tool_args_match_passes_on_subset_match() -> None:
    response = make_response(
        steps=[tool_call("refund", amount=10, order_id=99)], tool_calls_reported=True
    )
    ctx = make_ctx(response=response)
    spec = ToolArgsMatchJudge(judge="tool_args_match", tool="refund", args={"amount": 10})
    result = await rules.tool_args_match(spec, ctx)
    assert result.status == "pass"


async def test_tool_args_match_fails_on_value_mismatch() -> None:
    response = make_response(steps=[tool_call("refund", amount=5)], tool_calls_reported=True)
    ctx = make_ctx(response=response)
    spec = ToolArgsMatchJudge(judge="tool_args_match", tool="refund", args={"amount": 10})
    result = await rules.tool_args_match(spec, ctx)
    assert result.status == "fail"
