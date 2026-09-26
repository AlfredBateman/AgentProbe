"""Rule-based judges (SPEC.md §4.5): contains, contains_any, not_contains, regex,
json_schema, max_length, latency_under, tool_called, tool_not_called, tool_args_match.

Tool judges honor `AgentResponse.tool_calls_reported` (ADR 0012): when an agent doesn't
report tool calls, "no tool_call steps" means *unknown*, not "none were made", so a missing
report is an error, never a silent pass.
"""

import json
import re
import re._constants as _sre  # type: ignore[import-not-found]  # stdlib parser: no stubs
import re._parser as _sre_parser  # type: ignore[import-not-found]
from collections.abc import Iterable
from typing import Any, cast

import jsonschema
import regex as regexlib
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

# Suite YAML is user-supplied, so a regex pattern is hostile input (ADR 0015). Four guards,
# in the order they run:
# 1. Matching runs on the `regex` package with a timeout that covers the whole search, so
#    catastrophic backtracking (e.g. ^(a|aa)+$) ends as status=error instead of a hung worker.
REGEX_TIMEOUT_SECONDS = 0.25
# 2. Compiling has no timeout, and `regex` unrolls counted repeats while compiling: the 29
#    characters (?:(?:a{1000}){1000}){1000} would need a billion elements. Patterns are parsed
#    first with the stdlib parser (Python `re` syntax, which never unrolls) and refused when
#    their repeats would expand past this many elements, as RE2 refuses them.
MAX_REGEX_EXPANSION = 10_000
# 3. Bounds memory and keeps matching proportionate. Not the backtracking guard (1 is).
MAX_REGEX_INPUT = 100_000
# 4. Group nesting is bounded before the pattern reaches any parser, and checked first. The
#    stdlib parser recurses once per group, so ("*5000 + "a" + )"*5000 raises RecursionError.
#    That is caught below, but the half-built parse tree is then deep enough that *freeing*
#    it can recurse too, and that second RecursionError arrives as an unraisable exception in
#    whatever the process runs next (it surfaced as a flaky CI failure blamed on an unrelated
#    test). Counting parentheses first means the deep tree is never built. Real patterns nest
#    a few levels; 50 is far past anything legitimate.
MAX_REGEX_NESTING = 50

_REGEX_FLAGS = {  # suite flag -> (stdlib flag for parsing, regex flag for matching)
    "i": (re.IGNORECASE, regexlib.IGNORECASE),
    "m": (re.MULTILINE, regexlib.MULTILINE),
    "s": (re.DOTALL, regexlib.DOTALL),
    "x": (re.VERBOSE, regexlib.VERBOSE),
}
_REPEATS = (_sre.MAX_REPEAT, _sre.MIN_REPEAT, _sre.POSSESSIVE_REPEAT)


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


def _regex_error(reason: str) -> Judgment:
    return Judgment(status="error", score=0.0, reason=f"regex judge: {reason}")


def _expansion(items: Iterable[tuple[Any, Any]]) -> int:
    """How many elements a parsed pattern becomes once counted repeats are unrolled: each
    repeat multiplies its body by its count (the upper bound when there is one, so the
    estimate never undercounts; the lower bound for open-ended ones).
    """
    size = 0
    for op, arg in items:
        if op in _REPEATS:
            low, high, body = arg
            count = low if high == _sre.MAXREPEAT else high
            size += _expansion(body) * max(count, 1)
        elif op is _sre.SUBPATTERN:
            size += _expansion(arg[3])
        elif op is _sre.ATOMIC_GROUP:
            size += _expansion(arg)
        elif op in (_sre.ASSERT, _sre.ASSERT_NOT):
            size += _expansion(arg[1])
        elif op is _sre.BRANCH:
            size += sum(_expansion(branch) for branch in arg[1])
        elif op is _sre.GROUPREF_EXISTS:
            size += _expansion(arg[1]) + (_expansion(arg[2]) if arg[2] is not None else 0)
        else:
            size += 1
    return size


def _nesting_depth(pattern: str) -> int:
    """The deepest run of open groups, counting `(` outside escapes and character classes.
    Cheap and linear: it only has to be right enough to keep a pathological pattern away
    from the recursive parser (guard 4 above).
    """
    depth = deepest = 0
    escaped = in_class = False
    for char in pattern:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif in_class:
            in_class = char != "]"
        elif char == "[":
            in_class = True
        elif char == "(":
            depth += 1
            deepest = max(deepest, depth)
        elif char == ")":
            depth = max(0, depth - 1)
    return deepest


async def regex(spec: RegexJudge, ctx: JudgeContext) -> Judgment:
    if (depth := _nesting_depth(spec.pattern)) > MAX_REGEX_NESTING:
        return _regex_error(
            f"invalid pattern: groups nested too deeply ({depth}, limit {MAX_REGEX_NESTING})"
        )
    parse_flags = match_flags = 0
    for char in spec.flags:
        if char not in _REGEX_FLAGS:
            return _regex_error(f"unknown flag {char!r}")
        parse_flags |= _REGEX_FLAGS[char][0]
        match_flags |= _REGEX_FLAGS[char][1]
    try:
        expansion = _expansion(_sre_parser.parse(spec.pattern, parse_flags))
    except re.error as exc:
        return _regex_error(f"invalid pattern: {exc}")
    except RecursionError:
        return _regex_error("invalid pattern: nested too deeply")
    except OverflowError:  # a repeat count above the engine's maximum
        return _regex_error(f"pattern too large (limit {MAX_REGEX_EXPANSION:,} elements)")
    if expansion > MAX_REGEX_EXPANSION:
        return _regex_error(
            f"pattern too large: its counted repeats expand to {expansion:,} elements "
            f"(limit {MAX_REGEX_EXPANSION:,}); use * or + instead of large {{m,n}} counts"
        )
    try:
        pattern = regexlib.compile(spec.pattern, match_flags)
    except (regexlib.error, RecursionError) as exc:
        return _regex_error(f"invalid pattern: {exc}")

    truncated = len(ctx.output) > MAX_REGEX_INPUT
    text = ctx.output[:MAX_REGEX_INPUT]
    try:
        match = pattern.search(text, timeout=REGEX_TIMEOUT_SECONDS)
    except TimeoutError:
        return Judgment(
            status="error",
            score=0.0,
            reason=(
                f"regex judge: matching timed out after {REGEX_TIMEOUT_SECONDS}s "
                "(catastrophic backtracking?); rewrite the pattern"
            ),
            evidence={"truncated": truncated, "timeout_seconds": REGEX_TIMEOUT_SECONDS},
        )
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
