"""Rule-based judges (SPEC.md §4.5): contains, contains_any, not_contains, regex,
json_schema, max_length, latency_under, tool_called, tool_not_called, tool_args_match.

Tool judges honor `AgentResponse.tool_calls_reported` (ADR 0012): when an agent doesn't
report tool calls, "no tool_call steps" means *unknown*, not "none were made", so a missing
report is an error, never a silent pass.
"""

import json
import re
from typing import Any, cast

import jsonschema
from pydantic import JsonValue

from agentprobe_core.judges.types import JudgeContext, Judgment
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

# ponytail: a length cap (not a timeout) guards regex against catastrophic backtracking --
# stdlib `re` has no built-in timeout, and one enforced by a background thread can't be
# killed, so it would leak a runaway thread per hit instead of bounding the work. A cap
# bounds the worst case outright and needs nothing else.
MAX_REGEX_INPUT = 4_096

_REGEX_FLAGS = {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL, "x": re.VERBOSE}


async def contains(spec: ContainsJudge, ctx: JudgeContext) -> Judgment:
    found = spec.value in ctx.output
    return Judgment(
        status="pass" if found else "fail",
        score=1.0 if found else 0.0,
        reason=f"output {'contains' if found else 'does not contain'} {spec.value!r}",
    )


async def contains_any(spec: ContainsAnyJudge, ctx: JudgeContext) -> Judgment:
    matched = [value for value in spec.values if value in ctx.output]
    found = bool(matched)
    return Judgment(
        status="pass" if found else "fail",
        score=1.0 if found else 0.0,
        reason=(
            f"output contains {matched[0]!r}"
            if found
            else f"output contains none of {spec.values!r}"
        ),
        evidence={"matched": cast(JsonValue, matched)},
    )


async def not_contains(spec: NotContainsJudge, ctx: JudgeContext) -> Judgment:
    matched = [value for value in spec.values if value in ctx.output]
    violated = bool(matched)
    return Judgment(
        status="fail" if violated else "pass",
        score=0.0 if violated else 1.0,
        reason=(
            f"output contains forbidden value(s) {matched!r}"
            if violated
            else f"output contains none of {spec.values!r}"
        ),
        evidence={"matched": cast(JsonValue, matched)},
    )


async def regex(spec: RegexJudge, ctx: JudgeContext) -> Judgment:
    flags = 0
    for char in spec.flags:
        if char not in _REGEX_FLAGS:
            return Judgment(status="error", score=0.0, reason=f"regex judge: unknown flag {char!r}")
        flags |= _REGEX_FLAGS[char]
    try:
        pattern = re.compile(spec.pattern, flags)
    except re.error as exc:
        return Judgment(status="error", score=0.0, reason=f"regex judge: invalid pattern: {exc}")

    truncated = len(ctx.output) > MAX_REGEX_INPUT
    text = ctx.output[:MAX_REGEX_INPUT]
    match = pattern.search(text)
    found = match is not None
    reason = f"pattern matched at offset {match.start()}" if match else "pattern did not match"
    if truncated:
        reason += f" (output truncated to {MAX_REGEX_INPUT} chars before matching)"
    return Judgment(
        status="pass" if found else "fail",
        score=1.0 if found else 0.0,
        reason=reason,
        evidence={"truncated": truncated},
    )


async def json_schema(spec: JsonSchemaJudge, ctx: JudgeContext) -> Judgment:
    try:
        instance = json.loads(ctx.output)
    except json.JSONDecodeError as exc:
        return Judgment(status="fail", score=0.0, reason=f"output is not valid JSON: {exc}")
    try:
        jsonschema.validate(instance, spec.schema_)
    except jsonschema.SchemaError as exc:
        return Judgment(status="error", score=0.0, reason=f"invalid json_schema: {exc.message}")
    except jsonschema.ValidationError as exc:
        return Judgment(
            status="fail",
            score=0.0,
            reason=f"output does not match schema: {exc.message}",
            evidence={"path": cast(JsonValue, [str(part) for part in exc.absolute_path])},
        )
    return Judgment(status="pass", score=1.0, reason="output matches schema")


async def max_length(spec: MaxLengthJudge, ctx: JudgeContext) -> Judgment:
    length = len(ctx.output)
    ok = length <= spec.max_chars
    return Judgment(
        status="pass" if ok else "fail",
        score=1.0 if ok else 0.0,
        reason=(
            f"output length {length} is within {spec.max_chars}"
            if ok
            else f"output length {length} exceeds {spec.max_chars}"
        ),
        evidence={"length": length},
    )


async def latency_under(spec: LatencyUnderJudge, ctx: JudgeContext) -> Judgment:
    ok = ctx.latency_ms < spec.ms
    return Judgment(
        status="pass" if ok else "fail",
        score=1.0 if ok else 0.0,
        reason=(
            f"latency {ctx.latency_ms:.0f}ms is under {spec.ms}ms"
            if ok
            else f"latency {ctx.latency_ms:.0f}ms is not under {spec.ms}ms"
        ),
        evidence={"latency_ms": ctx.latency_ms},
    )


def _unreported(tool: str, judge: str) -> Judgment:
    return Judgment(
        status="error",
        score=0.0,
        reason=(
            f"{judge} judge for tool {tool!r}: the agent doesn't report tool calls, so "
            "whether it called this tool is unknown"
        ),
    )


async def tool_called(spec: ToolCalledJudge, ctx: JudgeContext) -> Judgment:
    if not ctx.response.tool_calls_reported:
        return _unreported(spec.tool, "tool_called")
    called = any(call.tool == spec.tool for call in ctx.response.tool_calls)
    return Judgment(
        status="pass" if called else "fail",
        score=1.0 if called else 0.0,
        reason=f"tool {spec.tool!r} {'was' if called else 'was not'} called",
    )


async def tool_not_called(spec: ToolNotCalledJudge, ctx: JudgeContext) -> Judgment:
    if not ctx.response.tool_calls_reported:
        return _unreported(spec.tool, "tool_not_called")
    called = any(call.tool == spec.tool for call in ctx.response.tool_calls)
    return Judgment(
        status="fail" if called else "pass",
        score=0.0 if called else 1.0,
        reason=f"tool {spec.tool!r} {'was' if called else 'was not'} called",
    )


def _is_subset(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return all(key in actual and actual[key] == value for key, value in expected.items())


async def tool_args_match(spec: ToolArgsMatchJudge, ctx: JudgeContext) -> Judgment:
    if not ctx.response.tool_calls_reported:
        return _unreported(spec.tool, "tool_args_match")
    calls = [call for call in ctx.response.tool_calls if call.tool == spec.tool]
    if not calls:
        return Judgment(status="fail", score=0.0, reason=f"tool {spec.tool!r} was not called")
    matched = any(_is_subset(spec.args, call.arguments) for call in calls)
    return Judgment(
        status="pass" if matched else "fail",
        score=1.0 if matched else 0.0,
        reason=(
            f"a call to {spec.tool!r} matched the expected args"
            if matched
            else f"no call to {spec.tool!r} matched the expected args {spec.args!r}"
        ),
        evidence={"calls": cast(JsonValue, [call.arguments for call in calls])},
    )
