"""execute_attempt / finalize_run / run_suite against fake adapters: tracing, typed errors,
timeouts, retries, concurrency, cancellation and the summary's statistics.
"""

import asyncio
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import JsonValue

from agentprobe_core.adapters.types import (
    AgentResponse,
    ErrorStep,
    MessageStep,
    TokenUsage,
    ToolCallStep,
)
from agentprobe_core.llm.config import Price
from agentprobe_core.llm.types import BudgetExceeded, Completion, Usage
from agentprobe_core.runner import (
    AttemptLimits,
    AttemptResult,
    RunOptions,
    RunSummary,
    check_results,
    execute_attempt,
    execute_with_retries,
    finalize_run,
    plan_attempts,
    run_suite,
)
from agentprobe_core.suite.schema import Case, Suite
from judgefakes import ScriptedLLM


def make_suite(cases: list[dict[str, Any]], runs_per_case: int = 1) -> Suite:
    return Suite.model_validate(
        {"suite": "s", "agent": "a", "runs_per_case": runs_per_case, "cases": cases}
    )


def case(id: str = "c", input: str = "hi", expect: list[dict[str, Any]] | None = None) -> Case:
    return Case.model_validate(
        {"id": id, "input": input, "expect": expect or [{"judge": "contains", "value": "ok"}]}
    )


def ok(output: str = "ok", **fields: Any) -> AgentResponse:
    return AgentResponse(
        output=output,
        steps=[
            MessageStep(role="user", content="hi"),
            ToolCallStep(tool="lookup", arguments={"id": "1"}),
            MessageStep(role="assistant", content=output),
        ],
        latency_ms=12.0,
        **{"tool_calls_reported": True, **fields},
    )


def failed(message: str, *, retryable: bool = False) -> AgentResponse:
    return AgentResponse(
        output="",
        steps=[ErrorStep(message=message)],
        latency_ms=1.0,
        error=message,
        retryable=retryable,
    )


@dataclass
class FakeAdapter:
    """Answers from `script` in order (the last entry repeats), after `delay_s`."""

    script: list[AgentResponse | Exception] = field(default_factory=lambda: [ok()])
    delay_s: float = 0.0
    calls: list[str] = field(default_factory=list)
    in_flight: int = 0
    max_in_flight: int = 0

    async def invoke(self, input: str, context: Sequence[JsonValue] = ()) -> AgentResponse:
        self.calls.append(input)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay_s)
        finally:
            self.in_flight -= 1
        answer = self.script[min(len(self.calls), len(self.script)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer


class NoSleepClock:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return time.monotonic()

    def now(self) -> Any:
        raise NotImplementedError

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


# --- execute_attempt ---------------------------------------------------------------------


async def test_attempt_captures_the_full_trace_and_accounting() -> None:
    response = ok(usage=TokenUsage(input_tokens=1000, output_tokens=500))
    result = await execute_attempt(
        case(expect=[{"judge": "contains", "value": "ok"}, {"judge": "tool_called", "tool": "x"}]),
        FakeAdapter([response]),
        agent_price=Price(input_per_mtok=1.0, output_per_mtok=4.0),
        attempt=3,
    )
    assert result.status == "failed"  # tool_called: x was never called
    assert result.attempt == 3
    assert result.input == "hi"
    assert result.response == response  # steps, tool calls with arguments, usage
    assert [(j.judge, j.status) for j in result.judgments] == [
        ("contains", "pass"),
        ("tool_called", "fail"),
    ]
    assert result.score == 0.5
    assert result.latency_ms == 12.0
    assert result.tokens == 1500
    assert result.cost_usd == pytest.approx((1000 * 1.0 + 500 * 4.0) / 1e6)
    assert result.error is None


async def test_attempt_passes_when_every_judge_passes() -> None:
    result = await execute_attempt(case(), FakeAdapter())
    assert (result.status, result.score, result.error) == ("passed", 1.0, None)
    assert result.cost_usd is None  # no price: unknown, not zero
    assert result.tokens is None


@pytest.mark.parametrize(
    ("response", "kind"),
    [
        (failed("HTTP 500 from the agent"), "agent"),
        (failed("could not connect", retryable=True), "unreachable"),
    ],
)
async def test_agent_failures_are_typed_errors(response: AgentResponse, kind: str) -> None:
    result = await execute_attempt(case(), FakeAdapter([response]))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.kind == kind
    assert result.response == response  # the error trace is kept
    assert result.judgments == []


async def test_an_adapter_exception_is_an_internal_error_not_a_crash() -> None:
    result = await execute_attempt(case(), FakeAdapter([RuntimeError("boom")]))
    assert result.error is not None
    assert (result.error.kind, result.error.message) == ("internal", "RuntimeError: boom")


async def test_agent_timeout_is_enforced() -> None:
    started = time.perf_counter()
    result = await execute_attempt(
        case(), FakeAdapter(delay_s=10), limits=AttemptLimits(agent_timeout_s=0.05)
    )
    assert time.perf_counter() - started < 2
    assert result.error is not None
    assert result.error.kind == "timeout"
    assert result.response is None


async def test_judge_timeout_is_a_judge_error() -> None:
    async def slow(spec: Any, ctx: Any) -> Any:
        await asyncio.sleep(10)

    result = await execute_attempt(
        case(), FakeAdapter(), {"contains": slow}, limits=AttemptLimits(judge_timeout_s=0.05)
    )
    assert result.error is not None
    assert result.error.kind == "judge"
    assert "timed out" in result.judgments[0].reason


async def test_judge_error_status_makes_the_attempt_an_error() -> None:
    # tool judges refuse to judge an agent that doesn't report tool calls (ADR 0012)
    result = await execute_attempt(
        case(expect=[{"judge": "tool_not_called", "tool": "x"}]),
        FakeAdapter([ok(tool_calls_reported=False)]),
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.kind == "judge"


async def test_budget_exhaustion_is_a_budget_error() -> None:
    async def broke(spec: Any, ctx: Any) -> Any:
        raise BudgetExceeded("run budget used up")

    result = await execute_attempt(case(), FakeAdapter(), {"contains": broke})
    assert result.error is not None
    assert (result.error.kind, result.error.message) == ("budget", "run budget used up")


async def test_judge_llm_spend_is_metered_per_attempt() -> None:
    verdict = json.dumps({"pass": True, "score": 1, "reason": "fine"})
    llm = ScriptedLLM(completions=[Completion(text=verdict, model="m", usage=Usage(cost_usd=0.25))])
    result = await execute_attempt(
        case(expect=[{"judge": "llm_rubric", "rubric": "be nice"}]), FakeAdapter(), llm=llm
    )
    assert result.status == "passed"
    assert result.judge_cost_usd == 0.25


async def test_consistency_is_not_judged_per_attempt() -> None:
    result = await execute_attempt(case(expect=[{"judge": "consistency"}]), FakeAdapter())
    assert (result.status, result.judgments) == ("passed", [])


async def test_a_case_without_input_is_an_error_result() -> None:
    no_input = Case.model_validate(
        {"id": "a", "attack": "tool_misuse", "expect": [{"judge": "contains", "value": "x"}]}
    )
    result = await execute_attempt(no_input, FakeAdapter())
    assert result.error is not None
    assert result.error.kind == "internal"


# --- finalize_run ------------------------------------------------------------------------


async def test_finalize_run_summarizes_cases_and_the_suite() -> None:
    suite = make_suite(
        [
            {"id": "a", "input": "x", "expect": [{"judge": "contains", "value": "ok"}]},
            {"id": "b", "input": "y", "expect": [{"judge": "consistency", "min_agreement": 0.9}]},
        ],
        runs_per_case=2,
    )
    adapter = FakeAdapter([ok(), ok("nope"), ok("aaaa"), ok("zzzz")])
    results = [
        await execute_attempt(suite.cases[0], adapter, attempt=0),
        await execute_attempt(suite.cases[0], adapter, attempt=1),
        await execute_attempt(suite.cases[1], adapter, attempt=0),
        await execute_attempt(suite.cases[1], adapter, attempt=1),
    ]
    summary = await finalize_run(list(reversed(results)), suite=suite)

    a, b = summary.cases
    assert (a.case_id, a.summary.passes, a.summary.attempts, a.label) == ("a", 1, 2, "flaky")
    [reason] = a.failures
    assert reason.startswith("contains:")
    assert b.label == "stable-pass"  # consistency doesn't change attempt pass counts
    [consistency] = b.consistency
    assert consistency.status == "fail"  # "aaaa" vs "zzzz"
    assert b.failures[-1].startswith("consistency:")
    assert summary.pass_rate == pytest.approx(0.75)
    assert summary.ci is not None
    assert summary.ci.lower <= 0.75 <= summary.ci.upper
    assert [(r.case_id, r.attempt) for r in summary.results] == [
        ("a", 0),
        ("a", 1),
        ("b", 0),
        ("b", 1),
    ]
    assert (summary.attempts, summary.errors, summary.infra_errors) == (4, 0, 0)
    assert summary.status == "completed"


async def test_errors_and_infra_errors_are_counted() -> None:
    suite = make_suite(
        [{"id": "a", "input": "x", "expect": [{"judge": "contains", "value": "ok"}]}]
    )
    results = [
        await execute_attempt(suite.cases[0], FakeAdapter([failed("500")]), attempt=0),
        await execute_attempt(
            suite.cases[0], FakeAdapter([failed("down", retryable=True)]), attempt=1
        ),
    ]
    summary = await finalize_run(results, suite=suite)
    assert (summary.errors, summary.infra_errors) == (2, 1)
    assert summary.cases[0].summary.errors == 2
    assert summary.cases[0].label == "stable-fail"


async def test_summary_round_trips_through_json() -> None:
    suite = make_suite(
        [{"id": "a", "input": "x", "expect": [{"judge": "contains", "value": "ok"}]}]
    )
    summary = await run_suite(suite, FakeAdapter())
    again = RunSummary.model_validate_json(summary.model_dump_json())
    assert again == summary
    assert again.case_summaries()["a"].pass_rate == 1.0


# --- run_suite ---------------------------------------------------------------------------


def slow_suite(cases: int, runs: int) -> Suite:
    return make_suite(
        [
            {"id": f"c{n}", "input": f"in{n}", "expect": [{"judge": "contains", "value": "ok"}]}
            for n in range(cases)
        ],
        runs_per_case=runs,
    )


async def test_parallel_beats_sequential() -> None:
    suite = slow_suite(cases=4, runs=2)

    async def timed(concurrency: int) -> tuple[float, FakeAdapter]:
        adapter = FakeAdapter(delay_s=0.1)
        started = time.perf_counter()
        summary = await run_suite(suite, adapter, options=RunOptions(concurrency=concurrency))
        assert summary.attempts == 8
        return time.perf_counter() - started, adapter

    sequential, one = await timed(1)
    parallel, many = await timed(8)
    assert one.max_in_flight == 1
    assert many.max_in_flight == 8
    assert sequential >= 0.8
    assert parallel < sequential / 3


async def test_concurrency_is_bounded() -> None:
    adapter = FakeAdapter(delay_s=0.02)
    await run_suite(slow_suite(cases=10, runs=2), adapter, options=RunOptions(concurrency=3))
    assert adapter.max_in_flight == 3
    assert len(adapter.calls) == 20


async def test_runs_per_case_override_and_streaming() -> None:
    seen: list[AttemptResult] = []

    async def on_result(result: AttemptResult) -> None:
        seen.append(result)

    summary = await run_suite(
        slow_suite(cases=2, runs=1),
        FakeAdapter(),
        options=RunOptions(runs_per_case=3),
        on_result=on_result,
    )
    assert summary.runs_per_case == 3
    assert len(seen) == summary.attempts == 6
    assert {(r.case_id, r.attempt) for r in seen} == {
        (f"c{c}", n) for c in (0, 1) for n in (0, 1, 2)
    }


async def test_retryable_errors_are_retried_with_backoff() -> None:
    clock = NoSleepClock()
    adapter = FakeAdapter([failed("down", retryable=True), failed("down", retryable=True), ok()])
    summary = await run_suite(
        slow_suite(cases=1, runs=1),
        adapter,
        options=RunOptions(max_retries=3, backoff_base_s=1.0, clock=clock),
    )
    [result] = summary.results
    assert (result.status, result.retries) == ("passed", 2)
    assert len(adapter.calls) == 3
    assert len(clock.sleeps) == 2
    assert all(0 <= s <= 1.0 * 2**n for n, s in enumerate(clock.sleeps))


async def test_retries_run_out_into_an_infra_error() -> None:
    adapter = FakeAdapter([failed("down", retryable=True)])
    summary = await run_suite(
        slow_suite(cases=1, runs=1),
        adapter,
        options=RunOptions(max_retries=2, clock=NoSleepClock()),
    )
    [result] = summary.results
    assert result.error is not None
    assert (result.error.kind, result.retries) == ("unreachable", 2)
    assert summary.infra_errors == 1


async def test_agent_errors_are_not_retried() -> None:
    adapter = FakeAdapter([failed("HTTP 500 from the agent")])
    summary = await run_suite(
        slow_suite(cases=1, runs=1),
        adapter,
        options=RunOptions(max_retries=3, clock=NoSleepClock()),
    )
    assert len(adapter.calls) == 1
    assert summary.results[0].retries == 0


async def test_timeouts_in_a_run_are_error_attempts() -> None:
    options = RunOptions(limits=AttemptLimits(agent_timeout_s=0.05), concurrency=4)
    summary = await run_suite(slow_suite(cases=2, runs=2), FakeAdapter(delay_s=10), options=options)
    assert summary.errors == 4
    assert {r.error.kind for r in summary.results if r.error} == {"timeout"}
    assert summary.pass_rate == 0.0


async def test_cancellation_stops_the_run_and_summarizes_what_finished() -> None:
    cancel = asyncio.Event()
    adapter = FakeAdapter(delay_s=0.05)

    async def on_result(result: AttemptResult) -> None:
        if len(finished) == 1:
            cancel.set()
        finished.append(result)

    finished: list[AttemptResult] = []
    started = time.perf_counter()
    summary = await run_suite(
        slow_suite(cases=10, runs=5),
        adapter,
        options=RunOptions(concurrency=2),
        on_result=on_result,
        cancel=cancel,
    )
    assert time.perf_counter() - started < 1  # 50 attempts x 50 ms / 2 would take 1.25 s
    assert summary.status == "cancelled"
    assert 2 <= summary.attempts < 50
    assert summary.attempts == len(finished)
    assert adapter.in_flight == 0  # in-flight attempts were cancelled, not orphaned
    calls = len(adapter.calls)
    await asyncio.sleep(0.1)
    assert len(adapter.calls) == calls  # and nothing new starts afterwards


async def test_cancelling_the_task_cancels_the_workers() -> None:
    adapter = FakeAdapter(delay_s=10)
    task = asyncio.create_task(run_suite(slow_suite(cases=4, runs=1), adapter))
    await asyncio.sleep(0.05)
    assert adapter.in_flight == 4
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert adapter.in_flight == 0


async def test_an_on_result_failure_aborts_the_run() -> None:
    async def on_result(result: AttemptResult) -> None:
        raise OSError("disk full")

    adapter = FakeAdapter(delay_s=0.01)
    with pytest.raises(OSError, match="disk full"):
        await run_suite(slow_suite(cases=5, runs=2), adapter, on_result=on_result)
    await asyncio.sleep(0.05)
    assert adapter.in_flight == 0


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"attack": "tool_misuse", "input": None}, "no input"),
        ({"mutations": 3}, "mutator"),
    ],
)
async def test_unrunnable_suites_are_refused_before_any_call(
    extra: dict[str, Any], message: str
) -> None:
    spec = {"id": "a", "input": "x", "expect": [{"judge": "contains", "value": "ok"}], **extra}
    adapter = FakeAdapter()
    with pytest.raises(ValueError, match=message):
        await run_suite(make_suite([spec]), adapter)
    assert adapter.calls == []


# --- the pieces the server reuses ----------------------------------------------------------


def test_plan_attempts_lists_every_case_attempt_in_order() -> None:
    plan = plan_attempts(slow_suite(cases=2, runs=1), 2)
    assert [(c.id, n) for c, n in plan] == [("c0", 0), ("c0", 1), ("c1", 0), ("c1", 1)]


async def test_check_results_accepts_only_distinct_planned_attempts() -> None:
    suite = slow_suite(cases=2, runs=2)
    done = (await run_suite(suite, FakeAdapter())).results
    check_results(suite, 2, done)  # a whole run
    check_results(suite, 2, done[:1])  # a partial one
    [c0] = [r for r in done if (r.case_id, r.attempt) == ("c0", 0)]
    for bad, message in [
        (c0.model_copy(update={"case_id": "nope"}), "'nope' attempt 0 is not in the run's plan"),
        (c0.model_copy(update={"attempt": 2}), "'c0' attempt 2 is not in the run's plan"),
        (c0.model_copy(update={"attempt": -1}), "'c0' attempt -1 is not in the run's plan"),
        (c0, "duplicate result for case 'c0' attempt 0"),
    ]:
        with pytest.raises(ValueError, match=message):
            check_results(suite, 2, [*done, bad] if bad is c0 else [bad])


async def test_execute_with_retries_retries_only_unreachable() -> None:
    clock = NoSleepClock()
    options = RunOptions(max_retries=2, clock=clock)
    down = FakeAdapter([failed("down", retryable=True), ok()])
    result = await execute_with_retries(case(), down, options=options, attempt=4)
    assert (result.status, result.retries, result.attempt) == ("passed", 1, 4)
    broken = FakeAdapter([failed("HTTP 500")])
    result = await execute_with_retries(case(), broken, options=options)
    assert (result.status, result.retries, len(broken.calls)) == ("error", 0, 1)


async def test_run_suite_resumes_from_completed_attempts() -> None:
    suite = slow_suite(cases=2, runs=2)
    first = await run_suite(suite, FakeAdapter([ok("nope")]))
    earlier = [r for r in first.results if (r.case_id, r.attempt) in {("c0", 0), ("c1", 1)}]
    adapter = FakeAdapter()
    seen: list[AttemptResult] = []

    async def on_result(result: AttemptResult) -> None:
        seen.append(result)

    summary = await run_suite(suite, adapter, completed=earlier, on_result=on_result)
    assert sorted(adapter.calls) == ["in0", "in1"]  # only the two missing attempts ran
    assert {(r.case_id, r.attempt) for r in seen} == {("c0", 1), ("c1", 0)}
    assert summary.attempts == 4
    assert [c.summary.passes for c in summary.cases] == [1, 1]  # the "nope"s still count
    assert summary.started_at == min(r.started_at for r in earlier)


async def test_cancelling_never_interrupts_on_result() -> None:
    cancel = asyncio.Event()
    saved: list[AttemptResult] = []

    async def on_result(result: AttemptResult) -> None:
        cancel.set()  # e.g. this result fails the run
        await asyncio.sleep(0.05)  # still saving when the cancel lands
        saved.append(result)

    summary = await run_suite(
        slow_suite(cases=5, runs=2),
        FakeAdapter(delay_s=0.01),
        options=RunOptions(concurrency=3),
        on_result=on_result,
        cancel=cancel,
    )
    assert summary.status == "cancelled"
    assert 1 <= len(saved) == summary.attempts < 10  # every delivered result was saved whole


async def test_an_on_result_failure_during_cancellation_still_raises() -> None:
    cancel = asyncio.Event()

    async def on_result(result: AttemptResult) -> None:
        cancel.set()
        await asyncio.sleep(0.01)
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        await run_suite(
            slow_suite(cases=2, runs=1), FakeAdapter(), on_result=on_result, cancel=cancel
        )
