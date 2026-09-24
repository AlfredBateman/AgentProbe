import time

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


async def test_regex_sees_long_outputs() -> None:
    # The cap used to be 4,096 chars (it stood in for a timeout); a match past it counts now.
    ctx = make_ctx(response=make_response("x" * 50_000 + "order #1234"))
    result = await rules.regex(RegexJudge(judge="regex", pattern=r"#\d+"), ctx)
    assert result.status == "pass"
    assert result.evidence["truncated"] is False


async def test_regex_catastrophic_backtracking_times_out_as_error() -> None:
    # OWASP's classic evil regex: on "aaa...a!" the engine tries every way to split the a's
    # into "a" and "aa" (Fibonacci(40), ~10^8 paths) before failing. The `regex` engine's
    # guards don't defuse this one, so only the timeout stops it.
    ctx = make_ctx(response=make_response("a" * 40 + "!"))
    spec = RegexJudge(judge="regex", pattern=r"^(a|aa)+$")
    started = time.perf_counter()
    result = await rules.regex(spec, ctx)
    elapsed = time.perf_counter() - started
    assert result.status == "error"
    assert "timed out" in result.reason
    assert result.evidence["timeout_seconds"] == rules.REGEX_TIMEOUT_SECONDS
    assert elapsed < rules.REGEX_TIMEOUT_SECONDS + 2  # bounded, whatever the input


@pytest.mark.parametrize(("length", "status"), [(28, "fail"), (5_000, "error")])
async def test_regex_textbook_nested_quantifier_is_bounded(length: int, status: str) -> None:
    # (a+)+$ is exponential for stdlib `re`. The `regex` engine's repeat guards make it
    # polynomial, not safe: measured unbounded, 500 a's take 0.2s, 1,000 take 1.6s, 2,000 take
    # 12s and 5,000 over 30s, so at 5,000 only the timeout stops it, on any machine.
    ctx = make_ctx(response=make_response("a" * length + "!"))
    started = time.perf_counter()
    result = await rules.regex(RegexJudge(judge="regex", pattern=r"(a+)+$"), ctx)
    assert result.status == status
    assert time.perf_counter() - started < rules.REGEX_TIMEOUT_SECONDS + 2


async def test_regex_compile_bomb_is_refused_without_compiling() -> None:
    # 29 characters that `regex` would unroll into 10^9 elements while compiling, which the
    # matching timeout doesn't cover.
    ctx = make_ctx(response=make_response("aaa"))
    spec = RegexJudge(judge="regex", pattern=r"(?:(?:a{1000}){1000}){1000}")
    started = time.perf_counter()
    result = await rules.regex(spec, ctx)
    assert time.perf_counter() - started < 1
    assert result.status == "error"
    assert "1,000,000,000 elements" in result.reason


@pytest.mark.parametrize(
    ("pattern", "status"),
    [(r"a{10000}", "fail"), (r"a{10001}", "error"), (r"(?:ab){5000}", "fail")],
)
async def test_regex_expansion_limit_boundary(pattern: str, status: str) -> None:
    ctx = make_ctx(response=make_response("aaa"))
    result = await rules.regex(RegexJudge(judge="regex", pattern=pattern), ctx)
    assert result.status == status


@pytest.mark.parametrize(
    ("pattern", "expansion"),
    [
        (r"abc", 3),
        (r"a{2,5}", 5),  # bounded: the upper count
        (r"a{1000,}", 1000),  # open-ended: the lower count
        (r"a*b+c?", 3),
        (r"(?:ab){3}", 6),
        (r"a|b{6}", 7),
        (r"(?:(?:a{10}){10}){10}", 1000),  # nesting multiplies
        (r"(?=x{7})(?!y)", 8),
        (r"(?>z{9})a{3}+", 12),
        (r"(a)(?(1)b{3}|c{4})", 8),
        (r"(?i:q{8})", 8),
    ],
)
def test_regex_expansion_estimate(pattern: str, expansion: int) -> None:
    assert rules._expansion(rules._sre_parser.parse(pattern, 0)) == expansion


@pytest.mark.parametrize(
    ("pattern", "flags", "output"),
    [
        # Everyday patterns are nowhere near the limit.
        (
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "",
            "id 1b4e28ba-2fa1-11d2-883f-0016d3cca427",
        ),
        (r"(?:\d{1,3}\.){3}\d{1,3}", "", "host 10.0.0.1"),
        # Python `re` features keep working: lookbehind, backreferences, verbose mode.
        (r"(?<=order )\d+", "", "order 1042"),
        (r"(\w)\1", "", "refund issued"),
        (r"refund \s+ issued  # comment", "x", "refund issued"),
    ],
)
async def test_regex_python_syntax_still_supported(pattern: str, flags: str, output: str) -> None:
    ctx = make_ctx(response=make_response(output))
    result = await rules.regex(RegexJudge(judge="regex", pattern=pattern, flags=flags), ctx)
    assert result.status == "pass", result.reason


@pytest.mark.parametrize(
    ("pattern", "reason"),
    [
        ("(" * 5_000 + "a" + ")" * 5_000, "nested too deeply"),
        (r"a{4294967296}", "too large"),  # above the engine's maximum repeat count
        (r"(?V1)a", "invalid pattern"),  # regex-only syntax: patterns are Python `re` syntax
    ],
)
async def test_regex_hostile_or_foreign_patterns_are_errors(pattern: str, reason: str) -> None:
    ctx = make_ctx(response=make_response("a"))
    result = await rules.regex(RegexJudge(judge="regex", pattern=pattern), ctx)
    assert result.status == "error"
    assert reason in result.reason


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
