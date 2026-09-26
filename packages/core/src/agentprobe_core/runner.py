"""How a run executes (SPEC.md §4.3, PLAN.md B1.7, ADR 0016). This is the only
implementation: the CLI's local run and the server runner both call `run_suite` (or
`execute_attempt` + `finalize_run`) and never reimplement the loop.

- `execute_attempt` sends one case input to the agent once, judges the response and returns
  an `AttemptResult` with the full trace. It never raises for a failure: timeouts, agent
  errors, judge errors and budget exhaustion come back as a typed `AttemptError`.
- `finalize_run` turns the attempts into per-case `CaseSummary`s (labels, Wilson intervals),
  runs the case-level `consistency` judges, and computes the suite pass rate with its CI,
  tokens and costs.
- `run_suite` expands cases x runs_per_case, runs attempts with bounded concurrency, retries
  retryable errors with backoff, supports cancellation, streams each result to `on_result`,
  and ends with `finalize_run`.

Agent outputs are untrusted data: they are stored and judged, never executed or rendered.
"""

import asyncio
import random
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from statistics import fmean
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, JsonValue

from agentprobe_core.adapters.types import AgentAdapter, AgentResponse
from agentprobe_core.judges.registry import evaluate
from agentprobe_core.judges.types import JudgeContext, Judgment, Status
from agentprobe_core.llm.config import Price
from agentprobe_core.llm.limits import Clock, SystemClock, with_backoff
from agentprobe_core.llm.types import (
    BudgetExceeded,
    Completion,
    Embeddings,
    LLMClient,
    Message,
    QuotaExhausted,
    Role,
)
from agentprobe_core.stats.summary import CaseSummary, Interval, Label, suite_stats
from agentprobe_core.suite.judges import JudgeSpec
from agentprobe_core.suite.schema import Case, StatisticsConfig, Suite

ErrorKind = Literal[
    "timeout",  # the agent didn't answer within the attempt's time limit
    "agent",  # the agent answered with a failure (bad status, bad JSON, exception, ...)
    "unreachable",  # never reached the agent (or it asked for a retry); retries ran out
    "judge",  # a judge couldn't evaluate the response
    "budget",  # the LLM budget or daily quota is used up
    "internal",  # an unexpected exception in AgentProbe or the adapter
]
# The run itself is broken, not the agent's behavior: the CLI exits 4 on these.
INFRA_ERRORS: frozenset[ErrorKind] = frozenset({"unreachable", "budget", "internal"})
CONSISTENCY = "consistency"  # case-level: judged in finalize_run, not per attempt
MAX_FAILURE_REASONS = 5


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AttemptError(_Model):
    kind: ErrorKind
    message: str

    @property
    def retryable(self) -> bool:
        return self.kind == "unreachable"


class JudgeResult(_Model):
    judge: str
    status: Status
    score: float
    reason: str
    evidence: dict[str, JsonValue] = {}

    @classmethod
    def of(cls, judge: str, judgment: Judgment) -> "JudgeResult":
        return cls(
            judge=judge,
            status=judgment.status,
            score=judgment.score,
            reason=judgment.reason,
            evidence=judgment.evidence,
        )


class AttemptResult(_Model):
    """One attempt of one case: the trace (`response`), every judge verdict and the
    accounting. `status` is `error` whenever `error` is set.
    """

    case_id: str
    attempt: int  # 0-based index within the case
    input: str
    status: Literal["passed", "failed", "error"]
    response: AgentResponse | None = None  # None: the agent never answered
    judgments: list[JudgeResult] = []
    error: AttemptError | None = None
    score: float | None = None  # mean judge score; None on error
    latency_ms: float | None = None
    tokens: int | None = None  # the agent's own, as it reported them
    cost_usd: float | None = None  # the agent's, estimated from `tokens` and its price
    judge_cost_usd: float = 0.0  # AgentProbe's own LLM spend on judging this attempt
    retries: int = 0
    started_at: AwareDatetime
    duration_ms: float


class CaseResult(_Model):
    case_id: str
    summary: CaseSummary
    pass_rate: float
    label: Label
    wilson: Interval
    consistency: list[JudgeResult] = []  # the case's consistency judges, if any
    failures: list[str] = []  # distinct failing judge reasons / errors, capped


class RunSummary(_Model):
    id: str
    suite: str
    agent: str
    status: Literal["completed", "cancelled"]
    runs_per_case: int
    statistics: StatisticsConfig
    started_at: AwareDatetime
    finished_at: AwareDatetime
    pass_rate: float | None  # mean of case pass rates; None if no attempt finished
    ci: Interval | None
    confidence: float
    attempts: int
    errors: int
    infra_errors: int
    tokens: int | None
    agent_cost_usd: float | None  # None unless every attempt's cost is known
    judge_cost_usd: float
    cases: list[CaseResult]
    results: list[AttemptResult]

    def case_summaries(self) -> dict[str, CaseSummary]:
        """Keyed by case id, for `stats.compare_runs`."""
        return {case.case_id: case.summary for case in self.cases}


@dataclass(frozen=True)
class AttemptLimits:
    # A backstop over the adapter's own timeout and retries (HTTP: 30 s x 3 by default).
    agent_timeout_s: float = 180.0
    judge_timeout_s: float = 120.0


@dataclass(frozen=True)
class RunOptions:
    runs_per_case: int | None = None  # None: the suite's
    concurrency: int = 4
    max_retries: int = 2  # per attempt, for retryable (`unreachable`) errors only
    backoff_base_s: float = 1.0
    backoff_cap_s: float = 30.0
    limits: AttemptLimits = AttemptLimits()
    statistics: StatisticsConfig | None = None  # None: the suite's `statistics:` block
    agent_price: Price | None = None
    clock: Clock = field(default_factory=SystemClock)


class _Metered:
    """Counts the LLM spend of one attempt (or one finalize) on a shared client."""

    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner
        self.cost_usd = 0.0

    async def complete(
        self,
        messages: Sequence[Message],
        role: Role,
        json_schema: dict[str, Any] | None = None,
        *,
        temperature: float | None = None,
        max_tokens: int = 1024,
    ) -> Completion:
        completion = await self._inner.complete(
            messages, role, json_schema, temperature=temperature, max_tokens=max_tokens
        )
        if not completion.cached:
            self.cost_usd += completion.usage.cost_usd
        return completion

    async def embed(self, texts: Sequence[str]) -> Embeddings:
        embeddings = await self._inner.embed(texts)
        if not embeddings.cached:
            self.cost_usd += embeddings.usage.cost_usd
        return embeddings


def _now() -> datetime:
    return datetime.now(UTC)


def _tokens(response: AgentResponse) -> int | None:
    usage = response.usage
    if usage.total_tokens is not None:
        return usage.total_tokens
    if usage.input_tokens is not None and usage.output_tokens is not None:
        return usage.input_tokens + usage.output_tokens
    return None


def _cost(response: AgentResponse, price: Price | None) -> float | None:
    usage = response.usage
    if price is None or usage.input_tokens is None or usage.output_tokens is None:
        return None
    return (
        usage.input_tokens * price.input_per_mtok + usage.output_tokens * price.output_per_mtok
    ) / 1_000_000


async def _judge(spec: JudgeSpec, ctx: JudgeContext, timeout_s: float) -> Judgment | AttemptError:
    """A judge's verdict; its failures become `error` verdicts. Budget exhaustion is
    returned as an `AttemptError`: every later LLM call would fail the same way.
    """
    try:
        async with asyncio.timeout(timeout_s):
            return await evaluate(spec, ctx)
    except TimeoutError:
        return Judgment("error", 0.0, f"judge timed out after {timeout_s:g}s")
    except (BudgetExceeded, QuotaExhausted) as exc:
        return AttemptError(kind="budget", message=str(exc))
    except Exception as exc:  # a judge bug or an LLM failure: a verdict, not a crash
        return Judgment("error", 0.0, f"{type(exc).__name__}: {exc}"[:500])


async def execute_attempt(
    case: Case,
    adapter: AgentAdapter,
    llm: LLMClient | None = None,
    limits: AttemptLimits = AttemptLimits(),  # noqa: B008 (frozen dataclass)
    *,
    attempt: int = 0,
    agent_price: Price | None = None,
) -> AttemptResult:
    """Runs one attempt of `case`. Pure and DB-free; never raises except on cancellation."""
    started, t0 = _now(), time.perf_counter()
    metered = _Metered(llm) if llm is not None else None
    input = case.input or ""

    def result(**fields: Any) -> AttemptResult:
        if (error := fields.get("error")) is not None:
            fields["status"] = "error"
            fields.setdefault("judgments", [])
            if not isinstance(error, AttemptError):
                raise TypeError(error)
        return AttemptResult(
            case_id=case.id,
            attempt=attempt,
            input=input,
            judge_cost_usd=metered.cost_usd if metered else 0.0,
            started_at=started,
            duration_ms=(time.perf_counter() - t0) * 1000,
            **fields,
        )

    if case.input is None:
        return result(
            error=AttemptError(
                kind="internal", message="the case has no input (attack generation isn't built)"
            )
        )
    try:
        async with asyncio.timeout(limits.agent_timeout_s):
            response = await adapter.invoke(case.input, case.context or ())
    except TimeoutError:
        message = f"no response within {limits.agent_timeout_s:g}s"
        return result(error=AttemptError(kind="timeout", message=message))
    except Exception as exc:  # adapters return agent failures; this is an adapter bug
        message = f"{type(exc).__name__}: {exc}"[:500]
        return result(error=AttemptError(kind="internal", message=message))

    accounting: dict[str, Any] = {
        "response": response,
        "latency_ms": response.latency_ms,
        "tokens": _tokens(response),
        "cost_usd": _cost(response, agent_price),
    }
    if response.error is not None:
        kind: ErrorKind = "unreachable" if response.retryable else "agent"
        return result(error=AttemptError(kind=kind, message=response.error), **accounting)

    ctx = JudgeContext(case=case, response=response, llm=metered)
    verdicts: list[JudgeResult] = []
    for spec in case.expect:
        if spec.judge == CONSISTENCY:
            continue
        judgment = await _judge(spec, ctx, limits.judge_timeout_s)
        if isinstance(judgment, AttemptError):
            return result(error=judgment, judgments=verdicts, **accounting)
        verdicts.append(JudgeResult.of(spec.judge, judgment))

    if errored := [v for v in verdicts if v.status == "error"]:
        message = f"{errored[0].judge}: {errored[0].reason}"
        return result(
            error=AttemptError(kind="judge", message=message), judgments=verdicts, **accounting
        )
    return result(
        status="failed" if any(v.status == "fail" for v in verdicts) else "passed",
        judgments=verdicts,
        score=fmean(v.score for v in verdicts) if verdicts else 1.0,
        **accounting,
    )


def _failures(attempts: Sequence[AttemptResult]) -> list[str]:
    reasons: dict[str, None] = {}  # ordered set
    for attempt in attempts:
        if attempt.error is not None:
            reasons[f"{attempt.error.kind} error: {attempt.error.message}"] = None
        for verdict in attempt.judgments:
            if verdict.status == "fail":
                reasons[f"{verdict.judge}: {verdict.reason}"] = None
    return list(reasons)[:MAX_FAILURE_REASONS]


def _mean(values: Sequence[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return fmean(known) if known else None


def _total(values: Sequence[float | None]) -> float | None:
    """The sum, or None unless every value is known (a partial sum would understate it)."""
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


async def finalize_run(
    results: Sequence[AttemptResult],
    *,
    suite: Suite,
    agent: str | None = None,
    runs_per_case: int | None = None,
    llm: LLMClient | None = None,
    statistics: StatisticsConfig | None = None,
    limits: AttemptLimits = AttemptLimits(),  # noqa: B008 (frozen dataclass)
    status: Literal["completed", "cancelled"] = "completed",
    started_at: datetime | None = None,
    run_id: str | None = None,
) -> RunSummary:
    """Summarizes a run's attempts. Cases without any attempt (a cancelled run) are left
    out. The `consistency` judge scores a case across its answered attempts; it is reported
    per case and doesn't change the attempts' pass/fail counts.
    """
    statistics = statistics or suite.statistics
    metered = _Metered(llm) if llm is not None else None
    by_case: dict[str, list[AttemptResult]] = {}
    for attempt in sorted(results, key=lambda r: r.attempt):
        by_case.setdefault(attempt.case_id, []).append(attempt)

    cases: list[CaseResult] = []
    for case in suite.cases:
        attempts = by_case.get(case.id)
        if not attempts:
            continue
        summary = CaseSummary(
            passes=sum(a.status == "passed" for a in attempts),
            attempts=len(attempts),
            errors=sum(a.status == "error" for a in attempts),
            mean_score=_mean([a.score for a in attempts]),
            mean_latency_ms=_mean([a.latency_ms for a in attempts]),
            cost_usd=_total([a.cost_usd for a in attempts]),
        )
        answered = [a.response for a in attempts if a.response and a.response.error is None]
        consistency: list[JudgeResult] = []
        if answered:
            ctx = JudgeContext(
                case=case,
                response=answered[0],
                llm=metered,
                case_outputs=[r.output for r in answered],
            )
            for spec in case.expect:
                if spec.judge == CONSISTENCY:
                    judgment = await _judge(spec, ctx, limits.judge_timeout_s)
                    if isinstance(judgment, AttemptError):
                        judgment = Judgment("error", 0.0, judgment.message)
                    consistency.append(JudgeResult.of(spec.judge, judgment))
        failures = _failures(attempts)
        failures += [f"consistency: {c.reason}" for c in consistency if c.status != "pass"]
        cases.append(
            CaseResult(
                case_id=case.id,
                summary=summary,
                pass_rate=summary.pass_rate,
                label=summary.label,
                wilson=summary.wilson(),
                consistency=consistency,
                failures=failures,
            )
        )

    stats = (
        suite_stats([c.summary for c in cases], resamples=statistics.bootstrap_resamples)
        if cases
        else None
    )
    order = {case.id: n for n, case in enumerate(suite.cases)}
    ordered = sorted(results, key=lambda r: (order.get(r.case_id, len(order)), r.attempt))
    tokens = [r.tokens for r in ordered if r.tokens is not None]
    return RunSummary(
        id=run_id or uuid.uuid4().hex,
        suite=suite.suite,
        agent=agent or suite.agent,
        status=status,
        runs_per_case=runs_per_case or suite.runs_per_case,
        statistics=statistics,
        started_at=started_at or (ordered[0].started_at if ordered else _now()),
        finished_at=_now(),
        pass_rate=stats.pass_rate if stats else None,
        ci=stats.ci if stats else None,
        confidence=stats.confidence if stats else 0.95,
        attempts=len(ordered),
        errors=sum(r.status == "error" for r in ordered),
        infra_errors=sum(r.error is not None and r.error.kind in INFRA_ERRORS for r in ordered),
        tokens=sum(tokens) if tokens else None,
        agent_cost_usd=_total([r.cost_usd for r in ordered]),
        judge_cost_usd=sum(r.judge_cost_usd for r in ordered)
        + (metered.cost_usd if metered else 0.0),
        cases=cases,
        results=ordered,
    )


def uses_llm(suite: Suite) -> bool:
    """Whether a judge in the suite calls an LLM: `llm_rubric`, or `consistency` (embeddings)."""
    return any(spec.judge in ("llm_rubric", CONSISTENCY) for c in suite.cases for spec in c.expect)


class _Retry(Exception):
    def __init__(self, result: AttemptResult) -> None:
        self.result = result


def plan_attempts(suite: Suite, runs_per_case: int) -> list[tuple[Case, int]]:
    """Every (case, attempt index) a run executes. Raises `ValueError` if the suite can't
    run. Mutation variants (`<id>#<n>`) will expand here once the mutator exists; until then
    a case that needs one is refused up front.
    """
    for case in suite.cases:
        if case.input is None:
            raise ValueError(
                f"case {case.id!r} has an attack but no input; attack generation isn't "
                "available yet, so give it a literal `input`"
            )
        if case.mutations is not None:
            raise ValueError(
                f"case {case.id!r} asks for mutations; the mutator isn't available yet"
            )
        if case.obfuscate or case.attack_params:
            field = "obfuscate" if case.obfuscate else "attack_params"
            raise ValueError(
                f"case {case.id!r} sets {field}; the attack library isn't available yet"
            )
    return [(case, n) for case in suite.cases for n in range(runs_per_case)]


def check_results(suite: Suite, runs_per_case: int, results: Sequence[AttemptResult]) -> None:
    """Raises `ValueError` unless every result is a distinct (case, attempt) of the run's
    plan: attempts executed elsewhere (e.g. uploaded by CI) can't invent cases, repeat an
    attempt, or give a case more attempts than `runs_per_case`.
    """
    planned = {(case.id, n) for case, n in plan_attempts(suite, runs_per_case)}
    seen: set[tuple[str, int]] = set()
    for result in results:
        key = (result.case_id, result.attempt)
        if key not in planned:
            raise ValueError(
                f"case {result.case_id!r} attempt {result.attempt} is not in the run's plan "
                f"({len(suite.cases)} cases x {runs_per_case} runs, attempts 0-{runs_per_case - 1})"
            )
        if key in seen:
            raise ValueError(
                f"duplicate result for case {result.case_id!r} attempt {result.attempt}"
            )
        seen.add(key)


async def execute_with_retries(
    case: Case,
    adapter: AgentAdapter,
    llm: LLMClient | None = None,
    options: RunOptions = RunOptions(),  # noqa: B008 (frozen dataclass)
    *,
    attempt: int = 0,
    rng: random.Random | None = None,
) -> AttemptResult:
    """`execute_attempt`, retrying an `unreachable` result up to `options.max_retries` times
    with full-jitter backoff. Nothing the agent may have acted on is retried. The result's
    `retries` says how many retries it took.
    """
    tries = 0

    async def once() -> AttemptResult:
        nonlocal tries
        tries += 1
        result = await execute_attempt(
            case,
            adapter,
            llm,
            options.limits,
            attempt=attempt,
            agent_price=options.agent_price,
        )
        if result.error is not None and result.error.retryable:
            raise _Retry(result)
        return result

    try:
        result = await with_backoff(
            once,
            max_retries=options.max_retries,
            clock=options.clock,
            rng=rng or random.Random(),  # noqa: S311 (jitter, not crypto)
            base_s=options.backoff_base_s,
            cap_s=options.backoff_cap_s,
            retry_on=_Retry,
        )
    except _Retry as exc:
        result = exc.result
    return result.model_copy(update={"retries": tries - 1})


async def run_suite(
    suite: Suite,
    adapter: AgentAdapter,
    llm: LLMClient | None = None,
    options: RunOptions = RunOptions(),  # noqa: B008 (frozen dataclass)
    *,
    agent: str | None = None,
    on_result: Callable[[AttemptResult], Awaitable[None]] | None = None,
    cancel: asyncio.Event | None = None,
    completed: Sequence[AttemptResult] = (),
) -> RunSummary:
    """Runs a whole suite. Raises `ValueError` before any call if the suite can't run.

    Attempts run `options.concurrency` at a time, through `execute_with_retries`. Setting
    `cancel` stops new attempts, cancels those in flight and returns a `cancelled` summary
    of the attempts that finished. `on_result` sees each final attempt as it finishes; an
    exception from it aborts the run. `completed` resumes a run: those (case, attempt)
    pairs aren't run again, and they count in the summary.
    """
    if options.concurrency < 1:
        raise ValueError(f"concurrency must be at least 1, got {options.concurrency}")
    runs_per_case = options.runs_per_case or suite.runs_per_case
    done = {(r.case_id, r.attempt) for r in completed}
    queue = [(c, n) for c, n in plan_attempts(suite, runs_per_case) if (c.id, n) not in done]
    queue.reverse()  # pop() from the end, in suite order
    started = min((r.started_at for r in completed), default=_now())
    rng = random.Random()  # noqa: S311 (jitter, not crypto)
    results: list[AttemptResult] = list(completed)

    async def attempt(case: Case, n: int) -> AttemptResult:
        return await execute_with_retries(case, adapter, llm, options, attempt=n, rng=rng)

    # A finished attempt is always delivered whole: cancelling the run interrupts agent
    # calls, never an on_result that is saving a result.
    deliveries: list[asyncio.Future[None]] = []

    async def worker() -> None:
        while queue:
            result = await attempt(*queue.pop())
            results.append(result)
            if on_result is not None:
                delivery = asyncio.ensure_future(on_result(result))
                deliveries.append(delivery)
                await asyncio.shield(delivery)

    async def work() -> None:
        async with asyncio.TaskGroup() as group:  # one failure cancels the other workers
            for _ in range(min(options.concurrency, len(queue))):
                group.create_task(worker())

    workers = asyncio.create_task(work())
    stop = asyncio.ensure_future(cancel.wait() if cancel else asyncio.Future[bool]())
    try:
        await asyncio.wait({workers, stop}, return_when=asyncio.FIRST_COMPLETED)
    finally:  # `cancel` was set, or run_suite itself was cancelled: stop the workers
        stop.cancel()
        if not workers.done():
            workers.cancel()
            try:
                await workers
            except asyncio.CancelledError:
                pass
        if unfinished := [d for d in deliveries if not d.done()]:
            await asyncio.wait(unfinished)
    cancelled = workers.cancelled()
    if not cancelled and (exc := workers.exception()) is not None:
        # An on_result failure; TaskGroup wraps it, so re-raise the original.
        raise exc.exceptions[0] if isinstance(exc, ExceptionGroup) else exc
    for delivery in deliveries:
        if (failure := delivery.exception()) is not None:
            raise failure  # an on_result that failed while the run was being cancelled
    return await finalize_run(
        results,
        suite=suite,
        agent=agent,
        runs_per_case=runs_per_case,
        llm=llm,
        statistics=options.statistics,
        limits=options.limits,
        status="cancelled" if cancelled else "completed",
        started_at=started,
    )
